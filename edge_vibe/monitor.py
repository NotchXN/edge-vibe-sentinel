"""Replay monitor with frozen baselines, persistence, hysteresis and quality gates."""

from copy import deepcopy

from .baseline import operating_context, validate_baseline
from .data import digest, quality_issues, timestamp, validate_window
from .dsp import extract_features


class Monitor:
    def __init__(self, model):
        self.model = deepcopy(validate_baseline(model))
        self.config = self.model["config"]
        self.states, self.streams, self.seen = {}, {}, set()

    def _reset_streaks(self, stream):
        for state in self.states.values():
            if state["stream"] == stream:
                state["breach_refs"].clear()
                state["clear_refs"].clear()

    def process(self, window):
        validate_window(window)
        stream = (window["device_id"], window["asset_id"])
        identity = (*stream, window["window_id"])
        if identity in self.seen:
            raise ValueError("Duplicate monitor window identity")
        stamp = timestamp(window["observed_at"])
        prior = self.streams.get(stream)
        if prior is not None and stamp <= prior["stamp"]:
            raise ValueError("Windows must be strictly chronological within each device/asset stream")
        features = extract_features(window, self.config)
        context = operating_context(window, self.config)
        key = digest(context) if context is not None else None
        if prior is not None and (prior["key"] != key or
                                 (stamp - prior["stamp"]).total_seconds() > self.config["max_gap_seconds"]):
            self._reset_streaks(stream)
        self.streams[stream] = {"stamp": stamp, "key": key}
        self.seen.add(identity)
        group = self.model["groups"].get(key)
        issues = quality_issues(window)
        record = {
            "schema_version": 1, "kind": "assessment", "record_id": digest([*identity, self.model["model_sha256"]]),
            "window_id": window["window_id"], "window_sha256": digest(window),
            "device_id": stream[0], "asset_id": stream[1], "observed_at": window["observed_at"],
            "provenance": window["provenance"], "operating_state": window["operating_state"],
            "cycle_phase": window.get("cycle_phase"), "rpm": window.get("rpm"), "load_pct": window.get("load_pct"),
            "temperature_c": window["temperature_c"], "model_sha256": self.model["model_sha256"],
            "context_key": key, "features": features, "quality_issues": issues,
            "assessment": None, "reasons": [], "thresholds": None, "alarm_active": False,
        }
        events = []
        if issues:
            record["assessment"] = "DATA_INVALID"
            record["reasons"] = issues
            self._reset_streaks(stream)
        elif window["operating_state"] not in ("steady", "actuating"):
            record["assessment"] = "SUPPRESSED_STATE"
            record["reasons"] = ["Startup, shutdown and stopped windows are not assessed against operating baselines"]
            self._reset_streaks(stream)
        elif key is None:
            record["assessment"] = "MISSING_CONTEXT"
            record["reasons"] = ["Speed/load or actuator-phase context is unavailable"]
            self._reset_streaks(stream)
        elif group is None or not group["ready"]:
            record["assessment"] = "NO_BASELINE" if group is None else "INSUFFICIENT_BASELINE"
            record["reasons"] = ["An approved, sufficiently populated baseline is required"]
            self._reset_streaks(stream)
        else:
            state = self.states.setdefault(key, {"stream": stream, "active": False, "breach_refs": [], "clear_refs": []})
            rms = features["vector_rms_g"]
            temperature = window["temperature_c"]
            record["thresholds"] = {
                "enter_rms_g": group["enter_rms_g"], "clear_rms_g": group["clear_rms_g"],
                "temperature_enter_c": self.config["temperature_enter_c"],
                "temperature_clear_c": self.config["temperature_clear_c"],
            }
            reasons = []
            if rms > group["enter_rms_g"]:
                reasons.append("Vector acceleration RMS exceeds its baseline-derived enter threshold")
            if temperature > self.config["temperature_enter_c"]:
                reasons.append("Housing temperature exceeds the configured enter threshold")
            reference = {"window_id": window["window_id"], "window_sha256": record["window_sha256"]}
            transition, evidence = None, None
            if not state["active"]:
                if reasons:
                    state["breach_refs"].append(reference)
                    record["assessment"] = "PENDING"
                    if len(state["breach_refs"]) >= self.config["enter_windows"]:
                        state["active"] = True
                        transition, evidence = "raised", list(state["breach_refs"])
                        state["breach_refs"].clear()
                        record["assessment"] = "ALARM"
                else:
                    state["breach_refs"].clear()
                    record["assessment"] = "NORMAL_WINDOW"
            else:
                recovered = rms <= group["clear_rms_g"] and temperature <= self.config["temperature_clear_c"]
                if recovered:
                    state["clear_refs"].append(reference)
                    record["assessment"] = "CLEAR_PENDING"
                    if len(state["clear_refs"]) >= self.config["clear_windows"]:
                        state["active"] = False
                        transition, evidence = "cleared", list(state["clear_refs"])
                        state["clear_refs"].clear()
                        record["assessment"] = "NORMAL_WINDOW"
                else:
                    state["clear_refs"].clear()
                    record["assessment"] = "ALARM"
            record["reasons"] = reasons
            if transition:
                events.append({
                    "schema_version": 1, "kind": "event", "transition": transition,
                    "record_id": digest([self.model["model_sha256"], key, window["window_id"], transition]),
                    "device_id": stream[0], "asset_id": stream[1], "provenance": window["provenance"],
                    "observed_at": window["observed_at"], "context_key": key,
                    "model_sha256": self.model["model_sha256"], "evidence": evidence,
                    "reasons": reasons, "vector_rms_g": rms, "temperature_c": temperature,
                })
        active_keys = sorted(k for k, state in self.states.items() if state["stream"] == stream and state["active"])
        record["active_context_keys"] = active_keys
        record["alarm_active"] = bool(active_keys)
        return record, events


def replay(windows, model):
    monitor = Monitor(model)
    assessments, events = [], []
    for window in windows:
        record, emitted = monitor.process(window)
        assessments.append(record)
        events.extend(emitted)
    return assessments, events


def summarize(assessments, events):
    statuses = sorted({r["assessment"] for r in assessments})
    latest = {}
    for record in assessments:
        latest[(record["device_id"], record["asset_id"])] = record["alarm_active"]
    return {"windows": len(assessments), "events_raised": sum(e["transition"] == "raised" for e in events),
            "events_cleared": sum(e["transition"] == "cleared" for e in events),
            "assessments": {s: sum(r["assessment"] == s for r in assessments) for s in statuses},
            "final_alarm_active": any(latest.values()) if latest else None,
            "final_alarm_by_stream": {f"{device}/{asset}": active for (device, asset), active in sorted(latest.items())}}
