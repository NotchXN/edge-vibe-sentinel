"""Dependency-free radix-2 FFT and explicitly normalized acceleration features."""

import cmath
from functools import lru_cache
import math

from .data import AXES, number, validate_window


@lru_cache(maxsize=16)
def _bit_reversal(n):
    order, j = [0] * n, 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        order[i] = j
    return tuple(order)


@lru_cache(maxsize=16)
def _twiddles(length):
    # Twiddle factors are accumulated exactly as the original loop did, so results are unchanged.
    root, weight, factors = cmath.exp(-2j * math.pi / length), 1 + 0j, []
    for _ in range(length // 2):
        factors.append(weight)
        weight *= root
    return tuple(factors)


@lru_cache(maxsize=16)
def hann_window(n):
    return tuple(0.5 - 0.5 * math.cos(2 * math.pi * i / n) for i in range(n))


def fft(values):
    n = len(values)
    if n == 0 or n & (n - 1):
        raise ValueError("FFT length must be a positive power of two")
    output = [complex(v) for v in values]
    for i, j in enumerate(_bit_reversal(n)):
        if i < j:
            output[i], output[j] = output[j], output[i]
    length = 2
    while length <= n:
        half, factors = length // 2, _twiddles(length)
        for offset in range(0, n, length):
            for k in range(half):
                first = output[offset + k]
                second = output[offset + k + half] * factors[k]
                output[offset + k], output[offset + k + half] = first + second, first - second
        length *= 2
    return output


def axis_features(samples, sample_rate, band_low, band_high):
    n = len(samples)
    mean = math.fsum(samples) / n
    signal = [v - mean for v in samples]
    rms = math.sqrt(math.fsum(v * v for v in signal) / n)
    peak = max(abs(v) for v in signal)
    hann = hann_window(n)
    spectrum = fft([v * weight for v, weight in zip(signal, hann)])
    gain, energy = math.fsum(hann), math.fsum(w * w for w in hann)
    df = sample_rate / n
    frequencies, amplitudes, psd = [], [], []
    for index in range(n // 2 + 1):
        factor = 1 if index in (0, n // 2) else 2
        magnitude = abs(spectrum[index])
        frequencies.append(index * df)
        amplitudes.append(factor * magnitude / gain)
        psd.append(factor * magnitude * magnitude / (sample_rate * energy))
    band_indices = [i for i, freq in enumerate(frequencies) if band_low <= freq <= band_high]
    if not band_indices:
        raise ValueError("Analysis band contains no FFT bins")
    dominant = max(band_indices, key=lambda i: amplitudes[i])
    features = {
        "mean_g": mean, "rms_g": rms, "peak_g": peak,
        "crest_factor": peak / rms if rms > 0 else None,
        "dominant_hz": frequencies[dominant] if amplitudes[dominant] > 1e-12 else None,
        "dominant_amplitude_g_peak": amplitudes[dominant],
        "band_rms_g": math.sqrt(math.fsum(psd[i] * df for i in band_indices)),
        "spectrum": {"frequency_hz": frequencies, "amplitude_g_peak": amplitudes},
    }
    for key in ("mean_g", "rms_g", "peak_g", "band_rms_g", "dominant_amplitude_g_peak"):
        number(features[key], "Derived " + key)
    return features


def extract_features(window, config):
    validate_window(window)
    sample_rate = window["sample_rate_hz"]
    low, high = config["band_low_hz"], config["band_high_hz"]
    if high > sample_rate / 2:
        raise ValueError("Analysis band exceeds the sample-rate Nyquist frequency")
    axes = {axis: axis_features(window["acceleration_g"][axis], sample_rate, low, high) for axis in AXES}
    total = math.sqrt(math.fsum(a["rms_g"] ** 2 for a in axes.values()))
    number(total, "Vector RMS")
    return {"axes": axes, "vector_rms_g": total, "sample_count": len(window["acceleration_g"]["x"]),
            "frequency_resolution_hz": sample_rate / len(window["acceleration_g"]["x"]),
            "band_hz": [low, high], "method": "demean-periodic-hann-v1"}
