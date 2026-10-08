# Hardware concept — not yet built

This release contains a computer simulator and analysis software. No PCB, validated schematic, pin assignment, firmware binary or purchasable complete kit is included. The following is a design direction for a later acquisition node.

## Candidate blocks

| Block | Candidate / role | Verification needed |
|---|---|---|
| Controller | ESP32-S3 development board with SPI, buffering and local storage | Exact board, available pins, throughput, memory and watchdog behavior |
| Acceleration | ADXL357 evaluation/breakout module with compatible supply/interface | Genuine module, voltage requirements, range, scaling, timing, filters and rigid mounting |
| Temperature | Contact temperature sensor on a repeatable housing location | Selected part, interface, contact quality, calibration and thermal response |
| Speed/context | Existing machine telemetry or a separate isolated sensing adapter | Signal levels, synchronization, speed/load meaning and actuator phase |
| Power | Protected conversion from the available machine supply | Supply tolerance, isolation requirements, fuse, surge protection, regulators and enclosure |
| Storage | Local flash/SD buffering appropriate to the node | Wear, interrupted writes, retention and recovery |

The [Analog Devices ADXL356/ADXL357 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/adxl356-357-357b.pdf) is the component reference. ADXL357 supports a 4 kHz output-data-rate configuration associated with a 1 kHz low-pass setting. A tentative physical experiment could capture 4096 samples at 4 kHz with a 10–800 Hz inspection band **after** measuring acceptable response and alias rejection. That is a candidate configuration, not a validated operating band. It is deliberately distinct from the 1024 Hz software demo and must have its own model context.

[Espressif ESP-DSP](https://github.com/espressif/esp-dsp) is a possible FFT/filtering library for a later ESP-IDF firmware port. It is not a dependency of this Python release. Porting requires repeating the numerical checks, confirming normalization and measuring MCU timing/memory use.

## Acquisition responsibilities

1. Mount the accelerometer rigidly on a suitable fixed housing, record orientation and a mount ID, and keep the location repeatable. Do not mount on moving shafts or exposed rotating parts.
2. Select a supported sensor range and filters. Convert raw counts to g using the selected device configuration and calibration. Do not rescale sample-rate metadata as a substitute for resampling.
3. Capture synchronous axes at a verified cadence; track FIFO overrun, missing samples, saturation and timing errors. Invalid acquisition must set the corresponding quality flags.
4. Attach measured or externally verified machine context. Unknown speed/load or actuator phase must remain unavailable rather than being invented.
5. Record housing temperature, UTC/offset timestamp, device/asset IDs, filter and calibration versions, and provenance distinct from `simulated`.
6. Export the documented JSONL windows first. Only after bench validation should the analysis and queue behavior move into firmware or a live host adapter.

Do not connect a machine's 24 V supply or industrial signals directly to logic pins. A complete power/interface design depends on the actual board and installation. This concept is not an electrical safety approval, certified machine-protection system or substitute for existing interlocks.

Before ordering parts, select the target motor/actuator, speed range, accessible mounting point, available supply and acquisition bandwidth. Those choices determine whether this candidate sensor/controller combination is suitable. Physical hardware completion remains a separate milestone.
