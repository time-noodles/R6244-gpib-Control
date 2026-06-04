import struct

def main():
    file_path = r"c:\Users\marconi\OneDrive - Science Tokyo\Python Scripts\libs\R6244-gpib-Control\ElectroChem_R6244.xls"
    with open(file_path, "rb") as f:
        data = f.read()

    # Find the SST record: record type 0x00FC
    # Format of record header: 2 bytes type, 2 bytes length
    offset = 0
    all_strings = []
    
    # We can scan the entire binary data for 0xFC, 0x00 (BIFF8 SST Record)
    # SST record code is 0x00FC (little-endian: FC 00)
    pos = 0
    while True:
        pos = data.find(b"\xfc\x00", pos)
        if pos == -1:
            break
        
        # Check header
        rec_type, rec_len = struct.unpack_low = struct.unpack_from("<HH", data, pos)
        if rec_type == 0x00FC:
            # Parse SST
            sst_data = data[pos + 4 : pos + 4 + rec_len]
            # SST structure:
            # 4 bytes: total strings
            # 4 bytes: unique strings
            # then string table
            if len(sst_data) >= 8:
                total, unique = struct.unpack_from("<II", sst_data, 0)
                # Parse strings
                idx = 8
                while idx < len(sst_data):
                    if idx + 2 > len(sst_data):
                        break
                    char_len = struct.unpack_from("<H", sst_data, idx)[0]
                    idx += 2
                    if idx + 1 > len(sst_data):
                        break
                    option = sst_data[idx]
                    idx += 1
                    
                    is_utf16 = option & 0x01
                    is_rich = option & 0x08
                    is_extend = option & 0x04
                    
                    rich_runs = 0
                    if is_rich:
                        if idx + 2 > len(sst_data):
                            break
                        rich_runs = struct.unpack_from("<H", sst_data, idx)[0]
                        idx += 2
                        
                    extend_len = 0
                    if is_extend:
                        if idx + 4 > len(sst_data):
                            break
                        extend_len = struct.unpack_from("<I", sst_data, idx)[0]
                        idx += 4
                        
                    bytes_per_char = 2 if is_utf16 else 1
                    byte_len = char_len * bytes_per_char
                    if idx + byte_len > len(sst_data):
                        # Might be continued in next record, just grab what we can
                        byte_len = len(sst_data) - idx
                        char_len = byte_len // bytes_per_char
                        
                    str_bytes = sst_data[idx : idx + byte_len]
                    idx += byte_len
                    
                    # skip rich formatting / extend data
                    idx += rich_runs * 4
                    idx += extend_len
                    
                    try:
                        if is_utf16:
                            s = str_bytes.decode("utf-16le", errors="ignore")
                        else:
                            s = str_bytes.decode("latin-1", errors="ignore")
                        all_strings.append(s)
                    except Exception:
                        pass
        pos += 2

    # Print all unique cell strings that might contain range info or commands
    print("Found", len(all_strings), "strings in SST.")
    keywords = ["range", "cmd", "r6244", "current", "voltage", "operate", "hold", "auto"]
    seen = set()
    for s in all_strings:
        s_clean = s.strip()
        if not s_clean:
            continue
        s_lower = s_clean.lower()
        if s_clean not in seen:
            seen.add(s_clean)
            if any(kw in s_lower for kw in keywords) or (len(s_clean) < 15 and any(c.isupper() for c in s_clean)):
                print(repr(s_clean))

if __name__ == "__main__":
    main()
