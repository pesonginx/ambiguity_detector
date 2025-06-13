from openpyxl import load_workbook
from openpyxl.styles import PatternFill

# Excel読み込み
wb = load_workbook("sample.xlsx")
ws = wb["データシート"]  # 処理対象シート名

color_map = {}
color_index = 1

# 判定対象の範囲：A1〜C10
source_range = ws["A1:C10"]

# オフセット列数（A〜C → D〜F → +3列）
column_offset = 3

for row in source_range:
    for cell in row:
        fill = cell.fill

        if isinstance(fill, PatternFill) and fill.fgColor.type == "rgb":
            color_code = fill.fgColor.rgb
        else:
            color_code = "NO_COLOR"

        if color_code not in color_map:
            color_map[color_code] = color_index
            color_index += 1

        # 対応するセル位置に番号を書き込み（+3列右にずらす）
        ws.cell(row=cell.row, column=cell.column + column_offset).value = color_map[color_code]

# 保存
wb.save("output_colored.xlsx")
