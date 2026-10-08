"""Deterministic motor/actuator waveforms; all acquisition is simulated."""

from datetime import datetime, timedelta, timezone
import math


def make_window(index, *, amplitude=0.075, state="steady", rpm=1500.0, load=45.0,
                temperature=52.0, phase=None, approved=False, identifier=None):
    size, sample_rate = 1024, 1024.0
    frequency = 12.0 if state == "actuating" else 50.0
    sensor = {"model": "simulated-accelerometer", "mount_id": "demo-rigid-mount-01",
              "axis_map": "x-radial-y-tangential-z-axial", "filter_id": "synthetic-bandlimited-v1",
              "calibration_id": "simulation-only", "range_g": 10.0}
    samples = {axis: [] for axis in ("x", "y", "z")}
    for i in range(size):
        t = i / sample_rate
        samples["x"].append(amplitude * math.sin(2 * math.pi * frequency * t) +
                            amplitude * 0.2 * math.sin(2 * math.pi * 125 * t) +
                            amplitude * 0.005 * math.sin(2 * math.pi * 230 * t + index))
        samples["y"].append(amplitude * 0.6 * math.sin(2 * math.pi * frequency * t + math.pi / 4))
        samples["z"].append(1.0 + amplitude * 0.25 * math.sin(2 * math.pi * 75 * t))
    origin = datetime(2026, 10, 3, 9, 0, tzinfo=timezone(timedelta(hours=7)))
    return {
        "schema_version": 1, "window_id": identifier or f"window-{index:03}",
        "device_id": "SIM-NODE-01", "asset_id": "DEMO-MOTOR-01", "provenance": "simulated",
        "observed_at": (origin + timedelta(seconds=index)).isoformat(),
        "sample_rate_hz": sample_rate, "operating_state": state, "cycle_phase": phase,
        "rpm": rpm, "load_pct": load, "temperature_c": temperature, "sensor": sensor,
        "approved_reference": approved,
        "quality": {"missing_samples": 0, "clipped": False, "timing_valid": True},
        "acceleration_g": samples,
    }


def reference_windows():
    records = []
    for index, factor in enumerate((0.97, 0.99, 1.0, 1.01, 1.03)):
        records.append(make_window(index, amplitude=0.075 * factor, approved=True, identifier=f"reference-motor-{index}"))
        records.append(make_window(index + 10, amplitude=0.11 * factor, state="actuating", phase="extend",
                                   rpm=None, approved=True, identifier=f"reference-extend-{index}"))
    for index in range(3):
        records.append(make_window(index + 20, amplitude=0.09, state="actuating", phase="retract",
                                   rpm=None, approved=True, identifier=f"reference-retract-{index}"))
    records.append(make_window(30, identifier="reference-not-approved"))
    invalid = make_window(31, approved=True, identifier="reference-invalid")
    invalid["quality"]["missing_samples"] = 4
    records.append(invalid)
    return records


def monitoring_windows():
    specifications = [
        {"state": "startup", "amplitude": 0.45}, {}, {}, {"rpm": 2100, "amplitude": 0.09}, {},
        {"state": "actuating", "phase": "extend", "rpm": None, "amplitude": 0.11},
        {"state": "actuating", "phase": "retract", "rpm": None, "amplitude": 0.09},
        {"amplitude": 0.27}, {"amplitude": 0.28}, {"amplitude": 0.29},
        {"amplitude": 0.27}, {"amplitude": 0.29}, {"amplitude": 0.31}, {"amplitude": 0.3},
        {"temperature": 65}, {"state": "stopped", "amplitude": 0.002, "rpm": 0}, {}, {},
        {"temperature": 84}, {"temperature": 85}, {"temperature": 86}, {},
        {"temperature": 74}, {"temperature": 73}, {}, {"rpm": None},
        {"state": "shutdown", "amplitude": 0.4}, {},
    ]
    records = [make_window(index + 60, **spec) for index, spec in enumerate(specifications)]
    records[9]["quality"]["missing_samples"] = 3
    records[21]["quality"]["clipped"] = True
    records[24]["sensor"]["mount_id"] = "demo-remounted-02"
    return records
