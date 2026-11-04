"""Synthetic sectioned plans: no copied user workbook or private course data."""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Border, Side


def sectioned_plan(path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    headers = ["序号", "课程代码", "课程名称", "开课学期", "学分"]
    for row, text in {
        1: "培养方案毕业总学分（164学分）", 2: "公共基础课程（38学分）",
        15: "通识教育课程模块（45.5学分）", 16: "通识教育必修（35.5学分）",
        45: "通识教育选修（10学分）", 46: "专业教育课程（80.5学分）",
        47: "专业必修课程（49.5学分）", 65: "专业选修课程（31学分）",
        94: "修读要求", 95: "选修清单不是每人必须修读的全部课程。",
        99: "专业选修要求包括跨专业选修2学分。", 100: "研究训练必选但不计入总学分。",
        108: "表2：英语课程的可选教学方案",
    }.items():
        sheet.cell(row, 1, text)
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
    for row in (3, 48, 66):
        for column, header in enumerate(headers, 1):
            sheet.cell(row, column, header)
    for row, values in {
        4: [1, "0001", "课程A", 1, 6], 5: [2, "0002", "课程B", 2, 2.5],
        17: [1, "0003", "课程C", "1,2", .25], 18: [2, "0004", "课程D", 2, 3],
        49: [1, "0005", "课程E", 3, 4], 67: [1, "0006", "选修方案A", 5, 2],
        68: [2, "0007", "研究训练", 7, 2],
        109: ["教学对象", "第一学期", "第二学期", "第三学期", "第四学期"],
        110: ["英语方案A", "英语1", "英语2", "英语3", "跨文化英语"],
        112: ["英语方案B", "英语2", "英语3", "跨文化英语", None],
    }.items():
        for column, value in enumerate(values, 1):
            sheet.cell(row, column, value)
    sheet["A14"], sheet["E14"] = "小计", "=SUM(E4:E13)"
    sheet["G66"], sheet["G68"] = "备注", "必选，不计入总学分"
    # Reproduce the physical K-column extent with blank F:K header cells.
    sheet["K112"].border = Border(bottom=Side(style="thin"))
    other = workbook.create_sheet("必修课程（开课学期）")
    other.append(["课程代码", "课程名称", "开课学期"])
    other.append(["0001", "课程A", 1])
    workbook.save(path)
    workbook.close()
    return path
