def merge_intervals(intervals):
    intervals.sort()  # Bug: mutates the caller's list.
    merged = []
    for start, end in intervals:
        if merged and start < merged[-1][1]:  # Bug: touching intervals stay separate.
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
