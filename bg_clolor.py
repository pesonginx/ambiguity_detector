from openpyxl import load_workbook
from openpyxl.styles import PatternFill

# Excelファイル読み込み
wb = load_workbook("sample.xlsx")
ws = wb.active

# 色コードと番号の対応を管理
color_map = {}
color_index = 1

# 判定対象の範囲（例：A1:A10）
for row in ws["A1:A10"]:
    for cell in row:
        fill = cell.fill

        # 背景色が設定されている場合のみ対象
        if isinstance(fill, PatternFill) and fill.fgColor.type == "rgb":
            color_code = fill.fgColor.rgb  # 例: 'FFFF0000'（赤）
        else:
            color_code = "NO_COLOR"  # 色なしとする

        # 色に対応する番号を登録
        if color_code not in color_map:
            color_map[color_code] = color_index
            color_index += 1

        # B列に番号を出力（例：A1→B1）
        ws.cell(row=cell.row, column=2).value = color_map[color_code]

# 保存
wb.save("output_colored.xlsx")
