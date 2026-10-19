from __future__ import annotations

import math


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile. q is between 0 and 1."""
    if not values:
        return None
    if not 0 <= q <= 1:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * q
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * weight)


def histogram_quantile(q: float, bounds: list[float], counts: list[int]) -> float | None:
    """Estimate a quantile from an explicit-bounds histogram.

    ``counts`` are per-bucket, not cumulative. The final bucket is +Inf and
    ``len(counts)`` should be ``len(bounds) + 1``. This does not average
    precomputed percentile values.
    """
    if not counts or q < 0 or q > 1:
        return None
    total = sum(int(c) for c in counts)
    if total <= 0:
        return None
    target = q * total
    cumulative = 0
    previous_cumulative = 0
    previous_bound = 0.0
    finite_bounds = [float(b) for b in bounds]
    for index, raw_count in enumerate(counts):
        count = int(raw_count)
        cumulative += count
        if index < len(finite_bounds):
            upper = finite_bounds[index]
        else:
            return finite_bounds[-1] if finite_bounds else previous_bound
        if cumulative >= target:
            if count <= 0:
                return upper
            fraction = (target - previous_cumulative) / count
            return previous_bound + (upper - previous_bound) * fraction
        previous_cumulative = cumulative
        previous_bound = upper
    return finite_bounds[-1] if finite_bounds else None


def merge_histograms(
    histograms: list[tuple[list[float], list[int]]],
) -> tuple[list[float], list[int], bool]:
    """Sum histograms that share bounds. Returns (bounds, counts, approximate)."""
    usable = [(list(map(float, b)), [int(c) for c in counts]) for b, counts in histograms if counts]
    if not usable:
        return [], [], False
    reference = usable[0][0]
    if all(bounds == reference and len(counts) == len(usable[0][1]) for bounds, counts in usable):
        merged = [0] * len(usable[0][1])
        for _, counts in usable:
            for index, count in enumerate(counts):
                merged[index] += count
        return reference, merged, False
    best_bounds, best_counts = max(usable, key=lambda item: sum(item[1]))
    return best_bounds, best_counts, True
