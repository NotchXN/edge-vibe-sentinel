# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-10-08

### Added

- `outbox prune [--keep N]` deletes acknowledged messages to bound local storage;
  pending messages are never removed.
- `final_alarm_by_stream` in analysis summaries, listing the latched alarm state of
  every device/asset stream.
- CI exercises `train`, `features`, `report`, every outbox command, a packaging install
  and the console script, and uploads the demo output as a workflow artifact.

### Fixed

- `validate_baseline` now checks `created_at`, `excluded_reference_ids`, group
  `context`/`reference_ids` structure and uniqueness, and nonnegative median/MAD
  statistics instead of accepting arbitrary values under a matching digest.

### Changed

- FFT bit-reversal order, twiddle factors and Hann windows are cached per length.
  Results are bit-identical to 0.1.0 (verified on all demo windows); replay is faster.
- `pyproject.toml` declares classifiers and keywords.

## [0.1.0] - 2026-10-03

- Initial standalone prototype: three-axis DSP, frozen context baselines, latched
  hysteretic alarms, chronological replay, offline HTML/CSV output, SQLite outbox,
  tests and CI.
