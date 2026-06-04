import os
import win32com.client

def search_sheet():
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    
    current_dir = os.getcwd()
    xls_path = os.path.join(current_dir, "ElectroChem_R6244.xls")
    
    wb = None
    try:
        wb = excel.Workbooks.Open(xls_path)
        sheet = wb.Sheets("Top")
        
        # 使用されているセル範囲
        used = sheet.UsedRange
        rows = used.Rows.Count
        cols = used.Columns.Count
        print(f"Searching Top sheet: {rows} rows x {cols} columns")
        
        keywords = ["limit", "limiter", "il", "vl", "pl", "nl", "imr", "vmr", "irn", "vrn", "gpib", "cmd", "command"]
        
        # メモリを節約し高速化するため、Value2をまとめて取得
        data = used.Value
        
        for r_idx, row in enumerate(data):
            for c_idx, val in enumerate(row):
                if val is not None:
                    val_str = str(val).lower()
                    if any(kw in val_str for kw in keywords):
                        # セルの位置 (1-based)
                        print(f"Row {r_idx+1}, Col {c_idx+1}: {repr(val)}")
                        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if wb:
            wb.Close(SaveChanges=False)
        excel.Quit()

if __name__ == "__main__":
    search_sheet()
