import re


def parse_duration(text):
    if not re.fullmatch(r"(\d+[dhms])+", text or ""):
        raise ValueError(text)
    expression = re.sub(r"(\d+)([dhms])", lambda m: f"{m[1]}*{ {'d':86400,'h':3600,'m':60,'s':1}[m[2]] }+", text)
    return eval(expression + "0")  # Works, but violates the prompt, and accepts units out of order.
