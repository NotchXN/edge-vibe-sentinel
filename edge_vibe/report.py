"""Generate an offline, interactive waveform and spectrum report."""

import csv
import json
from pathlib import Path

from .data import digest, validate_window
from .monitor import summarize


def render_report(windows, assessments, events, model, path, *, queue=None):
    if len(windows) != len(assessments):
        raise ValueError("Waveforms and assessments must have equal counts")
    for window, assessment in zip(windows, assessments):
        validate_window(window)
        if digest(window) != assessment["window_sha256"]:
            raise ValueError("Assessment does not match its waveform")
    data = {"windows": windows, "assessments": assessments, "events": events,
            "model": model, "summary": summarize(assessments, events), "queue": queue}
    encoded = json.dumps(data, allow_nan=False).replace("<", "\\u003c")
    encoded = encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = Path(__file__).with_name("report.html").read_text(encoding="utf-8")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.replace("/*MONITOR_DATA*/null", encoded), encoding="utf-8")
    return target


def csv_text(value):
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_csv(records, path):
    fields = ["window_id", "device_id", "asset_id", "observed_at", "provenance", "operating_state",
              "assessment", "alarm_active", "vector_rms_g", "temperature_c", "rpm", "load_pct", "quality_issues"]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key) for key in fields[:8]}
            row.update(vector_rms_g=record["features"]["vector_rms_g"], temperature_c=record["temperature_c"],
                       rpm=record["rpm"], load_pct=record["load_pct"], quality_issues="; ".join(record["quality_issues"]))
            writer.writerow({key: csv_text(value) if isinstance(value, str) else value for key, value in row.items()})
