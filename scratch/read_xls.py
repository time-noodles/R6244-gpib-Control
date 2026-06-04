import re

def main():
    file_path = r"c:\Users\marconi\OneDrive - Science Tokyo\Python Scripts\libs\R6244-gpib-Control\ElectroChem_R6244.xls"
    with open(file_path, "rb") as f:
        data = f.read()
    
    # Extract ASCII-like strings of length 3 to 100
    strings = re.findall(b"[a-zA-Z0-9_ -]{3,100}", data)
    
    # Filter and display strings that look like GPIB commands or relevant parameters
    keywords = [b"MD", b"VF", b"IF", b"F1", b"F2", b"IR", b"VR", b"RA", b"R0", b"R1", b"R2", b"R3", b"R4", b"R5", b"R6", b"RN"]
    
    seen = set()
    for s in strings:
        s_upper = s.upper()
        # If the string contains any of our key sequences
        if any(kw in s_upper for kw in keywords):
            decoded = s.decode("ascii", errors="ignore").strip()
            if decoded not in seen and len(decoded) < 50:
                seen.add(decoded)
                print(decoded)

if __name__ == "__main__":
    main()
