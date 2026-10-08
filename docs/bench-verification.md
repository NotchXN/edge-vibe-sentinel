# Bench verification plan

This plan describes work still required before using real measurements. Current numerical tests and demonstration data do not validate a sensor, installation or machine diagnosis.

## 1. Acquisition and calibration

Start with an isolated bench supply, the selected sensor/controller and a mechanically secure fixture. Verify all supply/interface levels against the exact component/module documents. Measure sample timing with an independent timing reference, count samples, and deliberately test overflow, missing samples and sensor saturation.

Check static orientations against gravity to validate axis mapping and scale. Establish uncertainty and compare dynamic acceleration against an appropriate calibrated reference or shaker across the intended band. Record filter, range, calibration and mounting IDs. Confirm that injected out-of-band vibration is adequately rejected; Nyquist checks alone do not establish anti-alias performance.

## 2. Feature equivalence

Export complete raw windows and compare host features with an independent trusted implementation and the reference instrumentation. Verify amplitude, RMS and band-energy normalization across bin-centered and off-bin tones, multiple tones and transients. For an MCU port, repeat identical golden vectors and measure worst-case computation time, buffering and memory use. Acceptance tolerances must reflect measurement uncertainty and the intended maintenance decision.

## 3. Operating baselines

Collect references only after external confirmation of suitable machine condition. Include representative speed/load combinations and actuator phases with repeated runs. Establish context boundaries empirically, including mounting repeatability and environmental changes. A five-window minimum is a software guard, not sufficient evidence for deployment.

Estimate within-context variation and false-alarm behavior. Tune limits and persistence with labeled observations that are separate from the training references. Freeze the accepted model and record its configuration/version before monitoring.

## 4. Failure and recovery

Use safe bench stimuli or recorded waveforms to cross RMS and temperature limits. Confirm repeated entry, hysteresis and required recovery windows. Interrupt breach and recovery sequences with bad timing, missing samples, clipping, context switches and long gaps. Confirm that existing alarms remain latched and their evidence is traceable.

Test multiple assets, restart the monitor and replay its history to reconstruct state. Restart the queue independently and verify pending records persist. Model future network outages by repeating exports, rejecting altered payloads and acknowledging only after receiver confirmation. Recovery behavior for interrupted writes and storage exhaustion still needs validation.

## 5. Field trial

Begin with observational logging alongside the existing maintenance process. Compare alerts to technician findings and reference measurements before using them to guide work. This project currently has no authority to shut down or protect a machine. Document limitations, disagreement cases, mounting changes and model revisions.
