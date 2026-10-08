# Waveform and output contract

Input is UTF-8 JSONL: one object per nonblank line. A BOM is accepted. Duplicate JSON keys, NaN/Infinity, duplicate device/asset/window identities and records above the parser's 3,000,000-character limit are rejected. Timestamps require an explicit timezone offset. Monitoring timestamps must increase strictly within each device/asset stream.

The following illustrates metadata only; replace each abbreviated axis with **64–8192 finite numeric samples**, with equal power-of-two lengths. Use the complete records in `examples/demo/windows.jsonl` as runnable input.

```json
{
  "schema_version": 1,
  "window_id": "capture-0001",
  "device_id": "node-01",
  "asset_id": "motor-01",
  "provenance": "bench-acquisition",
  "observed_at": "2026-10-03T09:00:00+07:00",
  "sample_rate_hz": 1024.0,
  "operating_state": "steady",
  "cycle_phase": null,
  "rpm": 1500.0,
  "load_pct": 45.0,
  "temperature_c": 52.0,
  "sensor": {
    "model": "sensor-model",
    "mount_id": "fixture-01",
    "axis_map": "x-radial-y-tangential-z-axial",
    "filter_id": "verified-acquisition-filter-v1",
    "calibration_id": "bench-calibration-01",
    "range_g": 10.0
  },
  "approved_reference": false,
  "quality": {"missing_samples": 0, "clipped": false, "timing_valid": true},
  "acceleration_g": {"x": [0.0], "y": [0.0], "z": [1.0]}
}
```

| Field | Contract |
|---|---|
| Identities/provenance | Nonempty strings, at most 160 characters |
| `sample_rate_hz` | Finite positive number, at most 100,000; analysis band must fit below/equal Nyquist |
| `operating_state` | `steady`, `actuating`, `startup`, `shutdown` or `stopped` |
| `cycle_phase` | Nonempty string required for `actuating` |
| `rpm` | Nonnegative number or null; required for a steady-state baseline match |
| `load_pct` | 0–100 number or null; required for eligible baseline matching |
| `temperature_c` | Finite housing-temperature reading in Celsius |
| Sensor metadata | Nonempty model/mount/axis/filter/calibration strings and positive range in g |
| `approved_reference` | Optional boolean, defaults false; training uses true only |
| Quality | Integer missing count >= 0, boolean clipped and timing-valid flags |
| Acceleration | Synchronized x/y/z arrays in g; booleans and numeric strings rejected |

The acquisition adapter must convert physical units, verify sampling timing and calibration, and set quality flags honestly. A window may carry invalid quality flags while retaining an array of samples: it can be inspected but cannot train or contribute to a decision streak. Missing samples must not be silently padded and marked valid. The range gate checks raw samples, including gravity offsets.

## Analysis artifacts

| Artifact | Contents |
|---|---|
| `baseline.json` | Schema, configuration, context groups, reference counts/IDs, medians/MAD, thresholds, readiness and model hash |
| `windows.jsonl` | Original waveform objects |
| `assessments.jsonl` | Identity/hash, context, features including spectrum, thresholds, quality, assessment and latched state |
| `events.jsonl` | Raised/cleared transitions, model/context hash and evidence window IDs/hashes |
| `measurements.csv` | Scalar summaries and status; text beginning with formula operators is prefixed with an apostrophe |
| `summary.json` | Counts and final stream-wide alarm state; null final state for empty input |
| `report.html` | Embedded raw measurements and results with no external scripts or data requests |

`config.json` must contain exactly the settings in `DEFAULT_CONFIG` in `baseline.py`. There is no partial configuration merge. Default analysis band is 10–400 Hz. Baseline reference minimum, speed/load bin widths, RMS multipliers, MAD multiplier, threshold floor, temperature limits, entry/recovery window counts and allowed gap are explicit in that file.

Outbox exports contain `schema_version: 1`, `kind: "outbox_batch"`, a batch UUID and ordered messages. Each message wraps a `record_id`, `payload_sha256` and payload. Queued assessments remove the spectrum arrays; events retain evidence references. Acknowledgment verifies payload hashes and local identity/content matches transactionally. No acknowledgment file is cryptographically authenticated.

CLI path checks prevent an output from replacing an explicitly supplied input or queue database. Output files in an existing analysis directory may be overwritten intentionally. Keep original acquisition data in a separate directory and select new output directories when preserving earlier analyses.
