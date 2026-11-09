import re

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
PATTERN = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def parse_duration(text):
    match = PATTERN.fullmatch(text)
    if not text or match is None:
        raise ValueError(f"invalid duration: {text!r}")
    return sum(int(value or 0) * factor for value, factor in zip(match.groups(), UNITS.values()))
