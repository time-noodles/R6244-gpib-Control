import re

def extract_strings(filename):
    with open(filename, 'rb') as f:
        data = f.read()
    
    # 3文字以上のASCII印字可能文字列を抽出
    ascii_strings = re.findall(b'[ -~]{3,}', data)
    
    # デコードしてテキストにする
    decoded = []
    for s in ascii_strings:
        try:
            decoded.append(s.decode('ascii'))
        except UnicodeDecodeError:
            pass
            
    print(f"Total ASCII strings extracted: {len(decoded)}")
    
    # GPIB コマンドに関係しそうなキーワードを検索
    keywords = ["MD0", "VF", "IF", "IRN", "VRN", "F1", "F2", "OP", "SO", "E", "H", "GPIB", "gpib", "R6244", "R6243"]
    
    # キーワードが含まれる文字列を表示
    print("\n--- Key Matches ---")
    for s in decoded:
        # キーワードのいずれかが含まれているか、または特定のGPIBコマンドパターン
        if any(kw in s for kw in keywords) or re.search(r'[A-Z]{2,}\s?\d+', s):
            # 長すぎるものは除外
            if len(s) < 100:
                print(s)

if __name__ == "__main__":
    extract_strings("ElectroChem_R6244.xls")
