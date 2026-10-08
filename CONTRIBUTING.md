# Contributing

Run `python -m unittest discover -s tests -v` and `python -m compileall -q edge_vibe tests` before submitting changes. No external Python dependencies are required for the reference implementation.

Explain the maintenance behavior that a change affects. For DSP changes, supply independent numerical expectations; for decision changes, cover quality interruptions, context switches, latched alarms and recovery. Preserve explicit simulated/real provenance and do not silently mark imported measurements as approved references.

Keep the documented data format and baseline feature-method identifier aligned with implementation. A change in feature definitions must not reuse old baselines without a deliberate migration. Avoid adding network delivery that acknowledges records before confirmed acceptance.

Include sanitized, clearly labeled fixtures with permission to redistribute. Never place customer production data, credentials or actual equipment identifiers in public demonstration artifacts.
