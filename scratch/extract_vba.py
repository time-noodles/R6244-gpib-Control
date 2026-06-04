import re

def main():
    file_path = r"c:\Users\marconi\OneDrive - Science Tokyo\Python Scripts\libs\R6244-gpib-Control\ElectroChem_R6244.xls"
    with open(file_path, "rb") as f:
        data = f.read()

    # VBA code is typically stored in unicode (UTF-16LE) or ASCII.
    # Let's search for ASCII strings and UTF-16LE strings.
    ascii_strings = re.findall(b"[\x20-\x7E\r\n\t]{4,200}", data)
    
    # UTF-16LE extraction
    utf16_strings = []
    # Search for UTF-16 pattern: [char]\x00[char]\x00...
    utf16_pattern = re.compile(b"(?:[\x20-\x7E][\x00]){4,200}")
    for m in utf16_pattern.finditer(data):
        raw = m.group()
        decoded = raw.decode("utf-16le", errors="ignore")
        utf16_strings.append(decoded)

    all_lines = []
    for s in ascii_strings:
        try:
            line = s.decode("ascii").strip()
            if line:
                all_lines.append(line)
        except Exception:
            pass
    for s in utf16_strings:
        line = s.strip()
        if line:
            all_lines.append(line)

    # Let's look for sections containing VBA keywords
    vba_keywords = ["sub", "function", "dim", "private", "public", "end sub", "call", "cells", "range", "write", "query"]
    printed = set()
    for line in all_lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in vba_keywords):
            if line not in printed and len(line) < 150:
                printed.add(line)
                print(line)

if __name__ == "__main__":
    main()
