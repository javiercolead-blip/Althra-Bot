"""Syncs the tracker to a Google Sheet (your phone-friendly daily queue).

Needs two env vars (set as GitHub Actions secrets):
  GOOGLE_SHEET_ID              – the long id in the sheet's URL
  GOOGLE_SERVICE_ACCOUNT_JSON  – the service-account key file's contents
The sheet must be shared (Editor) with the service account's email.
"""
from __future__ import annotations

import json
import os

from ..models import STATUSES, Opportunity
from . import COLOURS, COLUMNS, HEADERS, LEGEND, rows_to_dicts, to_row

TAB = "Tracker"
SUMMARY = "Summary"


def _rgb(hex_: str) -> dict:
    h = hex_.lstrip("#")
    return {k: int(h[i:i + 2], 16) / 255 for k, i in (("red", 0), ("green", 2), ("blue", 4))}


def configured() -> bool:
    return bool(os.environ.get("GOOGLE_SHEET_ID") and os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))


class GoogleSheet:
    def __init__(self) -> None:
        import gspread  # imported lazily so Excel-only use needs no Google deps

        creds = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        self.book = gspread.service_account_from_dict(creds).open_by_key(os.environ["GOOGLE_SHEET_ID"])
        self.ws = self._tab(TAB, rows=1000, cols=len(COLUMNS))

    def _tab(self, name: str, rows: int, cols: int):
        import gspread
        try:
            return self.book.worksheet(name)
        except gspread.WorksheetNotFound:
            return self.book.add_worksheet(name, rows=rows, cols=cols)

    def read(self) -> list[dict]:
        return rows_to_dicts(self.ws.get_all_values())

    def write(self, items: list[Opportunity]) -> None:
        # A scraped title starting with "=" must not become a formula.
        safe = lambda v: f"'{v}" if isinstance(v, str) and v[:1] in "=+@" else v  # noqa: E731
        values = [HEADERS] + [[safe(v) for v in to_row(o)] for o in items]
        rows_needed = len(values) + 500
        if self.ws.row_count < rows_needed:
            self.ws.add_rows(rows_needed - self.ws.row_count)
        self.ws.clear()
        self.ws.update(values, "A1", value_input_option="USER_ENTERED")
        self._format(rows_needed)
        self._summary()

    # ------------------------------------------------------------------ #
    def _format(self, nrows: int) -> None:
        sid = self.ws.id
        ncols = len(COLUMNS)
        meta = self.book.fetch_sheet_metadata({"fields": "sheets(properties.sheetId,conditionalFormats)"})
        existing = next((s.get("conditionalFormats", []) for s in meta["sheets"]
                         if s["properties"]["sheetId"] == sid), [])
        reqs: list[dict] = [{"deleteConditionalFormatRule": {"sheetId": sid, "index": 0}} for _ in existing]

        body = {"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows, "startColumnIndex": 0, "endColumnIndex": ncols}
        for i, (status, (bg, fg, bold)) in enumerate(COLOURS.items()):
            reqs.append({"addConditionalFormatRule": {"index": i, "rule": {
                "ranges": [body],
                "booleanRule": {
                    "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f'=$A2="{status}"'}]},
                    "format": {"backgroundColor": _rgb(bg), "textFormat": {"foregroundColor": _rgb(fg), "bold": bold}},
                }}}})

        reqs += [
            {"setDataValidation": {
                "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows, "startColumnIndex": 0, "endColumnIndex": 1},
                "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": s} for s in STATUSES]},
                         "showCustomUi": True, "strict": False}}},
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"backgroundColor": _rgb("#434343"),
                                               "textFormat": {"foregroundColor": _rgb("#FFFFFF"), "bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
            {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 2}},
                                       "fields": "gridProperties(frozenRowCount,frozenColumnCount)"}},
            {"setBasicFilter": {"filter": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": nrows,
                                                     "startColumnIndex": 0, "endColumnIndex": ncols}}}},
        ]
        for i, (_, width) in enumerate(COLUMNS):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": int(width * 7.5)}, "fields": "pixelSize"}})
        self.book.batch_update({"requests": reqs})

    def _summary(self) -> None:
        s = self._tab(SUMMARY, rows=30, cols=3)
        rows = [["Status", "Count", "What it means"]]
        rows += [[st, f'=COUNTIF({TAB}!A:A,"{st}")', meaning] for st, meaning in LEGEND]
        rows += [[], ["Total entries made", f"=SUM({TAB}!L:L)", ""]]
        s.clear()
        s.update(rows, "A1", value_input_option="USER_ENTERED")
        reqs = [{"repeatCell": {
            "range": {"sheetId": s.id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat"}}]
        for i, (st, _) in enumerate(LEGEND, start=1):
            bg, fg, bold = COLOURS[st]
            reqs.append({"repeatCell": {
                "range": {"sheetId": s.id, "startRowIndex": i, "endRowIndex": i + 1, "startColumnIndex": 0, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {"backgroundColor": _rgb(bg),
                                               "textFormat": {"foregroundColor": _rgb(fg), "bold": bold}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"}})
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": s.id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3},
            "properties": {"pixelSize": 560}, "fields": "pixelSize"}})
        self.book.batch_update({"requests": reqs})
