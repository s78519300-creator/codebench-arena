from durationkit import parse  # Hallucinated package.


def parse_duration(text):
    return parse(text).total_seconds()
