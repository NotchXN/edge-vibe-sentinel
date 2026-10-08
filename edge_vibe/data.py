"""Versioned waveform records, strict JSON, and provenance-aware contexts."""

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

AXES = ("x", "y", "z")
STATES = {"stopped", "steady", "startup", "shutdown", "actuating"}


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise ValueError(f"{name} must be nonempty text of at most 160 characters")
    return value


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("observed_at must be ISO text with a timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observed_at requires a timezone offset")
    return parsed


def strict_json(raw):
    def reject(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(raw, parse_constant=reject, object_pairs_hook=unique)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_window(window):
    if not isinstance(window, dict) or type(window.get("schema_version")) is not int or window["schema_version"] != 1:
        raise ValueError("Window requires integer schema_version 1")
    for key in ("window_id", "device_id", "asset_id", "provenance"):
        text(window.get(key), key)
    timestamp(window.get("observed_at"))
    state = window.get("operating_state")
    if not isinstance(state, str) or state not in STATES:
        raise ValueError("Unsupported operating_state")
    if state == "actuating":
        text(window.get("cycle_phase"), "Actuator cycle_phase")
    if not 0 < number(window.get("sample_rate_hz"), "Sample rate") <= 100000:
        raise ValueError("Sample rate must be greater than zero and at most 100 kHz")
    number(window.get("temperature_c"), "Housing temperature")
    for key in ("rpm", "load_pct"):
        if window.get(key) is not None:
            value = number(window[key], key)
            if value < 0 or (key == "load_pct" and value > 100):
                raise ValueError(f"Invalid {key}")
    sensor = window.get("sensor")
    if not isinstance(sensor, dict):
        raise ValueError("sensor metadata is required")
    for key in ("model", "mount_id", "axis_map", "filter_id", "calibration_id"):
        text(sensor.get(key), "sensor." + key)
    if number(sensor.get("range_g"), "Sensor range") <= 0:
        raise ValueError("Sensor range must be positive")
    quality = window.get("quality")
    if not isinstance(quality, dict):
        raise ValueError("quality metadata is required")
    if type(quality.get("missing_samples")) is not int or quality["missing_samples"] < 0:
        raise ValueError("missing_samples must be a nonnegative integer")
    if type(quality.get("clipped")) is not bool or type(quality.get("timing_valid")) is not bool:
        raise ValueError("Quality flags must be boolean")
    if type(window.get("approved_reference", False)) is not bool:
        raise ValueError("approved_reference must be boolean")
    samples = window.get("acceleration_g")
    if not isinstance(samples, dict) or set(samples) != set(AXES):
        raise ValueError("acceleration_g must contain x, y and z arrays")
    size = None
    for axis in AXES:
        values = samples[axis]
        if not isinstance(values, list):
            raise ValueError("Each axis must be an array")
        if size is None:
            size = len(values)
            if not 64 <= size <= 8192 or size & (size - 1):
                raise ValueError("Windows require a power-of-two length from 64 to 8192")
        if len(values) != size:
            raise ValueError("All axes must have equal sample counts")
        for value in values:
            number(value, "Acceleration sample")
    return window


def quality_issues(window):
    quality, issues = window["quality"], []
    if quality["missing_samples"]:
        issues.append("Missing samples")
    if quality["clipped"]:
        issues.append("Acquisition reports clipping")
    if not quality["timing_valid"]:
        issues.append("Acquisition timing is invalid")
    if any(abs(v) >= window["sensor"]["range_g"] for axis in AXES for v in window["acceleration_g"][axis]):
        issues.append("Sample reaches or exceeds configured sensor range")
    return issues


def load_jsonl(path, validator=None):
    records, seen = [], set()
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                if len(line) > 3_000_000:
                    raise ValueError("Record exceeds 3 MB")
                record = strict_json(line)
                if validator:
                    validator(record)
                if isinstance(record, dict) and "window_id" in record:
                    identity = (record["device_id"], record["asset_id"], record["window_id"])
                    if identity in seen:
                        raise ValueError("Duplicate window identity")
                    seen.add(identity)
                records.append(record)
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"Line {line_number}: {error}") from error
    return records


def write_json(value, path):
    encoded = json.dumps(value, indent=2, allow_nan=False)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(encoded + "\n", encoding="utf-8")


def write_jsonl(values, path):
    encoded = "".join(json.dumps(value, allow_nan=False) + "\n" for value in values)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(encoded, encoding="utf-8")
