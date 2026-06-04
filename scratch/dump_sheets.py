import os
import win32com.client

def dump_sheets():
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    
    current_dir = os.getcwd()
    xls_path = os.path.join(current_dir, "ElectroChem_R6244.xls")
    print(f"Opening workbook: {xls_path}")
    
    wb = None
    try:
        wb = excel.Workbooks.Open(xls_path)
        
        for sheet in wb.Sheets:
            print(f"\n=========================================")
            print(f"Sheet: {sheet.Name}")
            print(f"=========================================")
            
            # 使用されているセルの範囲を取得
            used_range = sheet.UsedRange
            rows = used_range.Rows.Count
            cols = used_range.Columns.Count
            print(f"Used area: {rows} rows x {cols} columns")
            
            # 100x100程度に制限して出力（大きすぎる場合のため）
            max_r = min(rows, 100)
            max_c = min(cols, 100)
            
            for r in range(1, max_r + 1):
                row_vals = []
                for c in range(1, max_c + 1):
                    val = used_range.Cells(r, c).Value
                    if val is not None:
                        row_vals.append(f"C{c}:{repr(val)}")
                if row_vals:
                    print(f"Row {r:02d}: " + " | ".join(row_vals))
                    
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        if wb:
            wb.Close(SaveChanges=False)
        excel.Quit()

if __name__ == "__main__":
    dump_sheets()
