import re

_RESPONSE_NUM_RE = re.compile(
    r'[+-]?\d+\.?\d*(?:[Ee][+-]?\d+)?'
)

def parse_response_value(response: str) -> float | None:
    search_str = response[3:] if len(response) > 3 else response
    m = _RESPONSE_NUM_RE.search(search_str)
    if m is None:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None

def test():
    # Various scientific formats that SMUs output
    test_cases = [
        "NDI+12.345E-06",
        "NDI -12.3456E-6",
        "NDI+0.01234E-3",
        "NDI+0001.234E-05",
        "NDI+12.34567-6",   # Some devices omit 'E'
        "NDI+1.23456e-05",
        "NDI+0.000023",     # Fixed point
        "NDI+00.00002",
        "NDI+0000.02E-3",
    ]
    for tc in test_cases:
        val = parse_response_value(tc)
        print(f"Response: {tc:<20} -> Parsed Float: {val:<15} -> formatted: {val*1e6:.3f} uA")

if __name__ == "__main__":
    test()
