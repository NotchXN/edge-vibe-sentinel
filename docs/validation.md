# Validation record — v0.1.0

Validated locally on Windows with Python **3.12.14** on **2026-10-03**.

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | **64 tests passed** |
| `python -m compileall -q edge_vibe tests` | Passed |
| Fresh-directory demo | 28 windows; 2 raised and 2 cleared events; no final latched alarm |
| Demo baseline | 3 contexts; 2 ready; 2 reference windows excluded |
| Demo SQLite queue | 32 inserted; duplicate insertion adds 0; 10 mock acknowledgments; 22 pending |
| Generated report | Embedded data counts checked; JavaScript syntax passed |
| Node report smoke test | Initialization, window/axis selection, inspection, search, quality filter and export handler passed using a DOM substitute |
| Wheel packaging | Wheel built locally and includes the HTML template and license |

The suite checks independent analytical/DFT/energy expectations, metadata and JSON rejection, context separation, frozen models, alarm persistence/hysteresis, quality/context/gap interruptions, local queue restarts and rollback, CLI workflows, output-path protection, HTML data escaping and CSV formula neutralization.

The standard setuptools PEP 517 build attempt encountered the host sandbox's temporary-directory access restriction. A direct local setuptools wheel build succeeded. No system package installation or network dependency download was performed. The normal installation command is documented for an ordinary Python environment; a fresh `pip install .` was not verified here.

GitHub Actions is configured for Windows/Linux and Python 3.11–3.13. Those remote jobs have **not** been run. Real-browser visual layout and interaction were **not** verified; the Node smoke test is not a browser substitute. Hardware accuracy, MCU acquisition/firmware, electrical interfaces, live transport, field thresholds and diagnostic performance are **unverified**.

All included waveforms have `simulated` provenance. A successful software test or quiet replay is not evidence that a real motor or actuator is healthy. See [bench-verification.md](bench-verification.md) for the remaining physical validation work.

## Revision 0.1.1 (8 October 2026)

- Full suite re-run on Linux with Python 3.13: 67 tests passed.
- New tests cover structural baseline validation, outbox pruning (pending messages retained, keep-N, re-queue), and per-stream alarm summaries. The cached-table FFT was checked bit-for-bit against the 0.1.0 implementation on all 43 demo windows.
- Report JavaScript executed against the regenerated demo output with the Node.js DOM-substitute smoke test (`tests/report-smoke.cjs`); still not a browser rendering test.
- Packaging verified with `python -m pip install .` followed by the console script `--version`.
- `examples/demo/` regenerated from the 0.1.1 code so bundled artifacts match the current output format.
- The remote GitHub Actions matrix has still not been run; the workflow now also performs the steps above.
