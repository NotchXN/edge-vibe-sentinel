"""SQLite store-and-forward queue. Exports are local; no network transport exists."""

import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .data import digest, number, strict_json, text, timestamp


def validate_message(record):
    if not isinstance(record, dict) or type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        raise ValueError("Outbox messages require schema_version 1")
    if not isinstance(record.get("kind"), str) or record["kind"] not in ("assessment", "event"):
        raise ValueError("Only assessment/event summaries can enter the outbox")
    for key in ("record_id", "device_id", "asset_id", "provenance"):
        text(record.get(key), key)
    timestamp(record.get("observed_at"))
    if record["kind"] == "assessment":
        features = record.get("features")
        if not isinstance(features, dict) or not isinstance(features.get("axes"), dict):
            raise ValueError("Assessment summaries require feature axes")
        if set(features["axes"]) != {"x", "y", "z"} or any(not isinstance(v, dict) for v in features["axes"].values()):
            raise ValueError("Feature axes must contain x/y/z objects")
        number(features.get("vector_rms_g"), "Vector RMS")
    else:
        if record.get("transition") not in ("raised", "cleared") or not isinstance(record.get("evidence"), list):
            raise ValueError("Events require a raised/cleared transition and evidence array")
    digest(record)  # Reject non-serializable or non-finite payloads.
    return record


class Outbox:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("CREATE TABLE IF NOT EXISTS messages (sequence INTEGER PRIMARY KEY, record_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0)")
        self.connection.commit()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.connection.close()

    def enqueue(self, records):
        inserted = 0
        with self.connection:
            for record in records:
                validate_message(record)
                identity, sha = record["record_id"], digest(record)
                existing = self.connection.execute("SELECT sha256 FROM messages WHERE record_id=?", (identity,)).fetchone()
                if existing:
                    if existing[0] != sha:
                        raise ValueError("Record ID already exists with different payload content")
                    continue
                self.connection.execute("INSERT INTO messages(record_id,payload,sha256) VALUES (?,?,?)",
                                        (identity, json.dumps(record, allow_nan=False), sha))
                inserted += 1
        return inserted

    def export_batch(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("Batch limit must be an integer 1-10000")
        rows = self.connection.execute("SELECT record_id,payload,sha256 FROM messages WHERE acknowledged=0 ORDER BY sequence LIMIT ?", (limit,)).fetchall()
        return {"schema_version": 1, "kind": "outbox_batch", "batch_id": str(uuid4()),
                "messages": [{"record_id": identity, "payload_sha256": sha, "payload": strict_json(payload)}
                             for identity, payload, sha in rows]}

    def acknowledge(self, batch):
        if not isinstance(batch, dict) or batch.get("kind") != "outbox_batch" or type(batch.get("schema_version")) is not int or batch["schema_version"] != 1:
            raise ValueError("Acknowledgment requires an exported outbox batch")
        text(batch.get("batch_id"), "Batch ID")
        if not isinstance(batch.get("messages"), list):
            raise ValueError("Batch messages must be an array")
        changed, seen = 0, set()
        with self.connection:
            for item in batch["messages"]:
                identity = text(item["record_id"], "Record ID")
                if identity in seen:
                    raise ValueError("Duplicate message in acknowledgment batch")
                seen.add(identity)
                validate_message(item["payload"])
                if item["payload"]["record_id"] != identity or digest(item["payload"]) != item["payload_sha256"]:
                    raise ValueError("Acknowledgment payload/hash mismatch")
                row = self.connection.execute("SELECT sha256,acknowledged FROM messages WHERE record_id=?", (identity,)).fetchone()
                if row is None or row[0] != item["payload_sha256"]:
                    raise ValueError("Acknowledgment does not match a queued message")
                if not row[1]:
                    self.connection.execute("UPDATE messages SET acknowledged=1 WHERE record_id=?", (identity,))
                    changed += 1
        return changed

    def prune(self, keep_acknowledged=0):
        """Delete acknowledged messages, optionally keeping the most recent ones.

        Pending messages are never removed: they have not been delivered. Deleting
        acknowledged messages frees local storage only; it does not change what a
        receiver already accepted.
        """
        if type(keep_acknowledged) is not int or not 0 <= keep_acknowledged <= 1_000_000:
            raise ValueError("keep_acknowledged must be an integer 0-1000000")
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM messages WHERE acknowledged=1 AND sequence NOT IN "
                "(SELECT sequence FROM messages WHERE acknowledged=1 ORDER BY sequence DESC LIMIT ?)",
                (keep_acknowledged,))
            deleted = cursor.rowcount
        return deleted

    def status(self):
        total, acknowledged = self.connection.execute("SELECT COUNT(*),COALESCE(SUM(acknowledged),0) FROM messages").fetchone()
        return {"total": total, "pending": total - acknowledged, "acknowledged": acknowledged}
