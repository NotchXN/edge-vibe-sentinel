# Roadmap

## Delivered in 0.1.0

Runnable simulation, documented three-axis DSP, approved frozen context baselines, hysteretic latched alerts, raw evidence references, chronological replay, offline HTML/CSV output and transactional SQLite queue. No hardware is required for this milestone. 0.1.1 adds stricter baseline-file validation, per-stream alarm state in summaries, outbox pruning and cached FFT tables.

## Next: real acquisition adapter

Select a motor or actuator and appropriate sensor/controller. Implement timestamped synchronous acquisition and the JSONL contract. Validate scale, cadence, filtering, mounting and quality flags against independent measurements. Collect approved real reference data with a separate provenance value.

## Next: firmware and restart recovery

Port verified features and decisions to the selected controller, benchmark resource use and repeat golden vectors. Define durable monitor-state checkpoints and interrupted-write recovery. Add bounded raw-window retention, configuration versioning, clock discontinuity handling and an explicit operational alarm-reset workflow.

## Next: delivery and maintenance workflow

Implement an authenticated receiver and network adapter with timeouts/retries, explicit receiver receipts and duplicate handling. Add queue quotas, automatic retention policy (manual `outbox prune` exists since 0.1.1), observability and asset-level maintenance notes. Validate upload behavior during outages and restarts. The current outbox provides local preparation only.

## Later, only with evidence

Evaluate order tracking, envelope analysis, actuator cycle alignment and anomaly models using independently labeled data. Introduce fault labels or life estimates only when the chosen asset, measurements and validation support them.
