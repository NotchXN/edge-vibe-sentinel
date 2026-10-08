# Signal processing and interpretation

All acceleration samples are in **g**. The parser requires three synchronized arrays, uniform sample-rate metadata and a power-of-two length. Actual uniform sampling must be established by acquisition hardware; metadata alone cannot prove it.

For each axis with N samples, subtract the arithmetic mean. This removes a static offset such as gravity for the window. Time-domain RMS is `sqrt(sum(x[i]^2)/N)`; peak is `max(abs(x[i]))`; crest factor is peak/RMS, or null when RMS is zero. These three features use the demeaned samples **without** a window function. Vector RMS is `sqrt(RMS_x^2 + RMS_y^2 + RMS_z^2)`.

## FFT amplitude

The periodic Hann weights are `w[i] = 0.5 - 0.5*cos(2*pi*i/N)`. The radix-2 FFT transforms `x[i]*w[i]` using the negative-exponent convention. Bin spacing is `fs/N`; the one-sided spectrum includes DC through Nyquist.

Peak amplitude in g at bin k is `factor * abs(X[k]) / sum(w)`, with factor 2 at interior bins and 1 at DC and Nyquist. This coherent-gain normalization recovers the peak amplitude of a bin-centered sinusoid. An off-bin tone spreads across bins and its strongest-bin amplitude generally underestimates its true amplitude. The dominant frequency is the strongest included bin in the configured analysis band; amplitudes below 1e-12 g yield a null dominant frequency.

## Band energy

One-sided PSD in g²/Hz is `factor * abs(X[k])^2 / (fs * sum(w^2))`. Band RMS is `sqrt(sum(PSD[k] * fs/N))` over bins whose centers lie within the inclusive lower/upper bounds. This energy normalization differs from amplitude normalization. Summing squared amplitude bins directly would overcount Hann leakage energy.

With the full spectrum, the PSD integral equals the Hann-weighted mean-square signal normalized by Hann energy. For a general finite transient, it need not equal unwindowed time-domain RMS exactly. Tone energy near a band boundary may be partly excluded. A narrow band without any bin centers is rejected.

The simulator uses **1024 samples at 1024 Hz**, giving one-second windows and 1 Hz bins, with a 10–400 Hz inspection band. Its tones are generated directly and do not establish a real sensor's noise, bandwidth, timing or anti-alias rejection.

## Baselines and limits

For each approved context, let m be median vector RMS and d the median absolute deviation from m. Define s = 1.4826*d. Defaults are:

```text
entry RMS = max(2.0*m, m + 6.0*s, 0.030 g)
clear RMS = max(1.4*m, m + 3.0*s, 0.024 g)
temperature entry > 80 C
temperature recovery <= 75 C
```

The code uses these demonstration constants through configuration; they are not universal machine limits. Five reference windows exercise minimum-count behavior and do not establish statistical reliability. The model is frozen during replay so degradation cannot gradually become a new normal automatically.

RMS alarming uses the full demeaned window, including frequencies outside the inspection band. Establish an acquisition filter and a physically useful frequency range before field use. The software does not apply a separate high-pass filter, integrate acceleration into velocity/displacement, track shaft orders, compute envelope spectra or identify defect frequencies.

Nyquist is a mathematical upper bound, not a sensor's usable flat-response bandwidth. A real acquisition design must account for sensor transfer functions, configured filters, alias rejection, mounting resonance, mechanical orientation and calibration. A change in sample rate, sample count, filter or mounting creates a new baseline context.

## Numerical evidence

Tests compare the FFT with an independent direct DFT, verify an impulse transform, use analytic sine RMS/peak/amplitude, check Nyquist amplitude scaling, confirm two-tone band energy and Parseval-normalized Hann energy, and verify removal of a static gravity offset. These validate the host calculation only; see [bench-verification.md](bench-verification.md) for physical validation still required.
