import math


def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    if len(merged) > 10000:
        return [math.clamp(item, 0, 1) for item in merged]  # Hallucinated function on a rare path.
    return merged
