"""Frozen, approved-reference baselines grouped by operating and sensor context."""

from copy import deepcopy
from datetime import datetime, timezone
import math
from statistics import median

from .data import digest, number, quality_issues, text, timestamp, validate_window
from .dsp import extract_features

DEFAULT_CONFIG = {
    "band_low_hz": 10.0, "band_high_hz": 400.0, "min_reference_windows": 5,
    "rpm_bin_width": 100.0, "load_bin_width": 20.0,
    "rms_enter_multiplier": 2.0, "rms_clear_multiplier": 1.4,
    "mad_multiplier": 6.0, "minimum_enter_rms_g": 0.03,
    "temperature_enter_c": 80.0, "temperature_clear_c": 75.0,
    "enter_windows": 3, "clear_windows": 2, "max_gap_seconds": 5.0,
}


def validate_config(config):
    if not isinstance(config, dict) or set(config) != set(DEFAULT_CONFIG):
        raise ValueError("Configuration must contain exactly the documented settings")
    for key, value in config.items():
        number(value, key)
    for key in ("min_reference_windows", "enter_windows", "clear_windows"):
        if type(config[key]) is not int or not 1 <= config[key] <= 10000:
            raise ValueError(f"{key} must be an integer 1-10000")
    if not 0 < config["band_low_hz"] < config["band_high_hz"]:
        raise ValueError("Analysis band must have positive increasing bounds")
    for key in ("rpm_bin_width", "load_bin_width", "minimum_enter_rms_g", "max_gap_seconds", "mad_multiplier"):
        if config[key] <= 0:
            raise ValueError(f"{key} must be positive")
    if not 1 <= config["rms_clear_multiplier"] < config["rms_enter_multiplier"]:
        raise ValueError("RMS enter multiplier must exceed clear multiplier, which must be at least 1")
    if config["temperature_clear_c"] >= config["temperature_enter_c"]:
        raise ValueError("Temperature clear limit must be below enter limit")
    return config


def operating_context(window, config):
    state = window["operating_state"]
    if state not in ("steady", "actuating"):
        return None
    if window.get("load_pct") is None or (state == "steady" and window.get("rpm") is None):
        return None
    return {
        "device_id": window["device_id"], "asset_id": window["asset_id"], "provenance": window["provenance"],
        "sensor": deepcopy(window["sensor"]), "sample_rate_hz": window["sample_rate_hz"],
        "sample_count": len(window["acceleration_g"]["x"]), "operating_state": state,
        "cycle_phase": window.get("cycle_phase") if state == "actuating" else None,
        "rpm_bin": math.floor(window["rpm"] / config["rpm_bin_width"]) if state == "steady" else None,
        "load_bin": math.floor(window["load_pct"] / config["load_bin_width"]),
    }


def train_baseline(windows, config=None):
    config = deepcopy(validate_config(DEFAULT_CONFIG if config is None else config))
    grouped, rejected, seen = {}, [], set()
    for window in windows:
        validate_window(window)
        identity = (window["device_id"], window["asset_id"], window["window_id"])
        if identity in seen:
            raise ValueError("Duplicate reference window identity")
        seen.add(identity)
        context = operating_context(window, config)
        if not window.get("approved_reference", False) or quality_issues(window) or context is None:
            rejected.append(window["window_id"])
            continue
        key = digest(context)
        grouped.setdefault(key, {"context": context, "values": [], "reference_ids": []})
        grouped[key]["values"].append(extract_features(window, config)["vector_rms_g"])
        grouped[key]["reference_ids"].append(window["window_id"])
    groups = {}
    for key, group in grouped.items():
        center = median(group["values"])
        mad = median(abs(v - center) for v in group["values"])
        sigma = 1.4826 * mad
        enter = max(center * config["rms_enter_multiplier"], center + config["mad_multiplier"] * sigma,
                    config["minimum_enter_rms_g"])
        clear = max(center * config["rms_clear_multiplier"], center + config["mad_multiplier"] * sigma / 2,
                    config["minimum_enter_rms_g"] * 0.8)
        groups[key] = {"context": group["context"], "reference_ids": group["reference_ids"],
                       "reference_count": len(group["values"]), "median_vector_rms_g": center,
                       "mad_vector_rms_g": mad, "enter_rms_g": enter, "clear_rms_g": clear,
                       "ready": len(group["values"]) >= config["min_reference_windows"]}
    model = {"schema_version": 1, "kind": "baseline", "created_at": datetime.now(timezone.utc).isoformat(),
             "config": config, "groups": groups, "excluded_reference_ids": rejected,
             "feature_method": "demean-periodic-hann-v1"}
    model["model_sha256"] = digest(model)
    return model


def validate_baseline(model):
    if not isinstance(model, dict) or type(model.get("schema_version")) is not int or model["schema_version"] != 1 or model.get("kind") != "baseline":
        raise ValueError("Expected baseline schema version 1")
    if model.get("feature_method") != "demean-periodic-hann-v1":
        raise ValueError("Unsupported feature method")
    validate_config(model["config"])
    if model.get("model_sha256") != digest({key: value for key, value in model.items() if key != "model_sha256"}):
        raise ValueError("Baseline content digest does not match")
    timestamp(model.get("created_at"))
    excluded = model.get("excluded_reference_ids")
    if not isinstance(excluded, list) or any(not isinstance(v, str) for v in excluded):
        raise ValueError("excluded_reference_ids must be a list of window IDs")
    if not isinstance(model["groups"], dict):
        raise ValueError("Baseline groups must be an object")
    for key, group in model["groups"].items():
        if not isinstance(group, dict) or not isinstance(group.get("context"), dict):
            raise ValueError("Each baseline group must be an object with a context")
        if key != digest(group["context"]):
            raise ValueError("Baseline context digest does not match")
        count = group.get("reference_count")
        ids = group.get("reference_ids")
        if type(count) is not int or count < 1 or not isinstance(ids, list) or len(ids) != count:
            raise ValueError("Invalid reference count")
        for identifier in ids:
            text(identifier, "Reference window ID")
        if len(set(ids)) != count:
            raise ValueError("Reference window IDs must be unique within a group")
        if number(group.get("median_vector_rms_g"), "Median vector RMS") < 0 or number(group.get("mad_vector_rms_g"), "MAD") < 0:
            raise ValueError("Baseline statistics must be nonnegative")
        if type(group["ready"]) is not bool or group["ready"] != (count >= model["config"]["min_reference_windows"]):
            raise ValueError("Baseline readiness conflicts with reference count")
        if not 0 <= number(group["clear_rms_g"], "Clear threshold") < number(group["enter_rms_g"], "Enter threshold"):
            raise ValueError("Baseline thresholds must have positive hysteresis")
    return model
