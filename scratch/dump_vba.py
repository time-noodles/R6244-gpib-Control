import os
import win32com.client

def dump_vba_and_sheets():
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    
    current_dir = os.getcwd()
    xls_path = os.path.join(current_dir, "ElectroChem_R6244.xls")
    print(f"Opening workbook: {xls_path}")
    
    wb = None
    try:
        wb = excel.Workbooks.Open(xls_path)
        
        # 1. シート内のボタンや図形に登録されているマクロ名をダンプ
        print("\n--- Shapes and Macros ---")
        for sheet in wb.Sheets:
            print(f"Sheet: {sheet.Name}")
            for shape in sheet.Shapes:
                try:
                    print(f"  Shape: {shape.Name}, OnAction: {shape.OnAction}")
                except Exception:
                    pass
                    
        # 2. VBAプロジェクトのダンプを試みる
        print("\n--- VBA Project ---")
        try:
            vb_project = wb.VBProject
            for component in vb_project.VBComponents:
                name = component.Name
                print(f"Component: {name}")
                try:
                    code_module = component.CodeModule
                    count = code_module.CountOfLines
                    if count > 0:
                        code = code_module.Lines(1, count)
                        output_file = os.path.join(current_dir, f"scratch_{name}.txt")
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(code)
                        print(f"  -> Dumped {count} lines of code to scratch_{name}.txt")
                except Exception as e:
                    print(f"  -> Failed to dump code module: {e}")
        except Exception as e:
            print(f"VBA Project Access failed (probably due to Excel macro security settings): {e}")
            print("You can allow programmatic access to Visual Basic Project in Excel Settings, or we will analyze strings.")

    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        if wb:
            wb.Close(SaveChanges=False)
        excel.Quit()

if __name__ == "__main__":
    dump_vba_and_sheets()
