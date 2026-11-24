"""Writes data/tracker.xlsx with dropdowns and colour-coded statuses."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ..models import STATUSES, Opportunity
from . import COLOURS, COLUMNS, HEADERS, LEGEND, rows_to_dicts, to_row

TAB = "Tracker"


def _fill(hex_: str) -> PatternFill:
    return PatternFill(start_color=hex_[1:], end_color=hex_[1:], fill_type="solid")


def read_excel(path: Path) -> list[dict]:
    if not path.exists():
        return []
    wb = load_workbook(path, data_only=True)
    if TAB not in wb.sheetnames:
        return []
    return rows_to_dicts([list(r) for r in wb[TAB].iter_rows(values_only=True)])


def write_excel(path: Path, items: list[Opportunity]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = TAB
    ws.append(HEADERS)
    for o in items:
        ws.append(to_row(o))

    last = max(ws.max_row, 2)
    end_col = get_column_letter(len(COLUMNS))
    for i, (_, width) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = _fill("#434343")
        c.alignment = Alignment(vertical="center")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{end_col}{last}"
    link_col = HEADERS.index("Link") + 1
    for r in range(2, ws.max_row + 1):
        c = ws.cell(r, link_col)
        if c.value:
            c.hyperlink = c.value
            c.font = Font(color="1155CC", underline="single")

    # Status dropdown, applied well past the data so new hand-added rows get it too.
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"A2:A{last + 500}")

    # Whole-row colour by status.
    rng = f"A2:{end_col}{last + 500}"
    for status, (bg, fg, bold) in COLOURS.items():
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=[f'$A2="{status}"'], fill=_fill(bg), font=Font(color=fg[1:], bold=bold)))

    # Summary tab: live counts + colour legend.
    s = wb.create_sheet("Summary")
    s.append(["Status", "Count", "What it means"])
    for c in s[1]:
        c.font = Font(bold=True)
    for status, meaning in LEGEND:
        s.append([status, f'=COUNTIF({TAB}!A:A,"{status}")', meaning])
        bg, fg, bold = COLOURS[status]
        for c in s[s.max_row]:
            c.fill = _fill(bg)
            c.font = Font(color=fg[1:], bold=bold)
    s.append([])
    s.append(["Total entries made", f"=SUM({TAB}!L:L)"])
    s.column_dimensions["A"].width = 18
    s.column_dimensions["C"].width = 80

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
