"""Read-only workbook display representation; never a query data source."""
from __future__ import annotations

from datetime import date, datetime
import json
from io import BytesIO
import time

from dbfox_dlc_api import (
    ATTACHMENT_RESOURCE_KIND, AttachmentResourceHandle, BaseModel, DlcOperationError,
    DlcOperationSpec, Field, ToolInputError,
)
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.utils.datetime import to_excel, WINDOWS_EPOCH
from pydantic import JsonValue

from .workbook import checkpoint, preflight

PREVIEW_MAX_BYTES = 8 * 1024 * 1024
PREVIEW_MAX_ROWS = 10_001
PREVIEW_MAX_COLUMNS = 128
# A normal openpyxl workbook retains all sheets. Bound that allocation before
# loading styles; a small selected sheet cannot hide an enormous sibling sheet.
PREVIEW_MAX_WORKBOOK_CELLS = 125_000


class WorkbookViewInput(BaseModel):
    attachment_id: str = Field(min_length=1, max_length=128)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class WorkbookSheetInput(WorkbookViewInput):
    sheet: str = Field(min_length=1, max_length=128)


class WorkbookViewOutput(BaseModel):
    data: dict[str, JsonValue]


def _color(value):
    return "#" + value.rgb[-6:] if value and value.type == "rgb" and isinstance(value.rgb, str) else None


def metadata(source: AttachmentResourceHandle) -> dict:
    stats = preflight(source, lambda: False, time.monotonic() + 60)
    workbook = load_workbook(BytesIO(source.path.read_bytes()), read_only=True, data_only=False, keep_links=False)
    try:
        return {"attachment_id": source.id, "sha256": source.content_sha256,
                "sheets": [{"name": ws.title, "state": ws.sheet_state, **stats[ws._worksheet_path]} for ws in workbook],
                "limits": {"max_rows": PREVIEW_MAX_ROWS, "max_columns": PREVIEW_MAX_COLUMNS,
                           "max_workbook_cells": PREVIEW_MAX_WORKBOOK_CELLS, "max_response_bytes": PREVIEW_MAX_BYTES}}
    finally:
        workbook.close()


def preview(source: AttachmentResourceHandle, sheet: str) -> dict:
    deadline = time.monotonic() + 60
    stats = preflight(source, lambda: False, deadline)
    if sum(s["cells"] + s["merged_cells"] for s in stats.values()) > PREVIEW_MAX_WORKBOOK_CELLS:
        raise ToolInputError("此工作簿超过125,000个单元格的预览内存预算；分析能力采用独立限制，不提供截断预览。")
    # Read just the selected sheet's path/extent using the library's reader.
    descriptor = load_workbook(BytesIO(source.path.read_bytes()), read_only=True, data_only=False, keep_links=False)
    try:
        if sheet not in descriptor.sheetnames or descriptor[sheet].sheet_state != "visible":
            raise ToolInputError("指定工作表不存在或为隐藏工作表。")
        extent = stats[descriptor[sheet]._worksheet_path]
        if extent["rows"] > PREVIEW_MAX_ROWS or extent["columns"] > PREVIEW_MAX_COLUMNS:
            raise ToolInputError("此工作表超过预览的10,001行或128列限制；没有静默截断。")
    finally:
        descriptor.close()
    workbook = load_workbook(BytesIO(source.path.read_bytes()), read_only=False, data_only=False, keep_links=False)
    cached = None
    try:
        ws = workbook[sheet]
        formulas = {c.coordinate for row in ws.iter_rows(max_row=extent["rows"], max_col=extent["columns"]) for c in row if c.data_type == "f"}
        cache_values = {}
        if formulas:
            cached = load_workbook(BytesIO(source.path.read_bytes()), read_only=True, data_only=True, keep_links=False)
            for row in cached[sheet].iter_rows(max_row=extent["rows"], max_col=extent["columns"]):
                for cell in row:
                    if getattr(cell, "coordinate", None) in formulas:
                        cache_values[cell.coordinate] = cell.value
        styles, cells, byte_count = {}, [], 0
        for row in ws.iter_rows(max_row=extent["rows"], max_col=extent["columns"]):
            checkpoint(lambda: False, deadline)
            for cell in row:
                if cell.value is None and not cell.has_style:
                    continue
                style_id = str(cell.style_id)
                if style_id not in styles:
                    style = {"font": {"name": cell.font.name, "size": cell.font.sz, "bold": cell.font.b, "italic": cell.font.i, "color": _color(cell.font.color)},
                             "fill": _color(cell.fill.fgColor) if cell.fill.patternType == "solid" else None,
                             "format": cell.number_format,
                             "align": {"horizontal": cell.alignment.horizontal, "vertical": cell.alignment.vertical, "wrap": cell.alignment.wrap_text},
                             "borders": {side: {"style": getattr(cell.border, side).style, "color": _color(getattr(cell.border, side).color)}
                                         for side in ("top", "right", "bottom", "left") if getattr(cell.border, side) and getattr(cell.border, side).style}}
                    byte_count += len(json.dumps(style, ensure_ascii=False).encode())
                    styles[style_id] = style
                formula = cell.value if cell.coordinate in formulas else None
                value = cache_values.get(cell.coordinate) if formula else cell.value
                native_type = "date" if isinstance(value, (datetime, date)) else "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "text"
                if native_type == "date":
                    value = to_excel(value, epoch=WINDOWS_EPOCH)
                item = {"r": cell.row - 1, "c": cell.column - 1, "v": value, "type": native_type, "style": style_id}
                if formula is not None:
                    item["formula"] = formula if isinstance(formula, str) else "[unsupported formula]"
                byte_count += len(json.dumps(item, ensure_ascii=False).encode())
                if byte_count > PREVIEW_MAX_BYTES - 65_536:
                    raise ToolInputError("工作表预览表示超过8 MiB限制；未返回截断内容。")
                cells.append(item)
        frozen = coordinate_to_tuple(ws.freeze_panes) if ws.freeze_panes else (1, 1)
        display = {"name": sheet, "rows": max(1, extent["rows"]), "columns": max(1, extent["columns"]),
                   "cells": cells, "merges": [{"r": a.min_row - 1, "c": a.min_col - 1, "rs": a.max_row - a.min_row + 1, "cs": a.max_col - a.min_col + 1} for a in ws.merged_cells.ranges],
                   "rowHeights": {str(i - 1): d.height * 4 / 3 for i, d in ws.row_dimensions.items() if d.height},
                   "columnWidths": {str(d.min - 1): round(d.width * 7 + 5) for d in ws.column_dimensions.values() if d.width},
                   "hiddenRows": [i - 1 for i, d in ws.row_dimensions.items() if d.hidden],
                   "freeze": {"rows": frozen[0] - 1, "columns": frozen[1] - 1}}
        return {"attachment_id": source.id, "source": source.display_name, "sha256": source.content_sha256,
                "styles": styles, "sheets": [display], "omissions": ["charts", "images", "conditional-formatting", "rich-text-runs", "theme-colors"],
                "readonly": True, "formula_mode": "cached_only"}
    finally:
        workbook.close()
        if cached is not None:
            cached.close()


def register_workbook_views(host) -> None:
    def invoke(data, context):
        reference = next((ref for ref in context.resource_refs if ref.kind == ATTACHMENT_RESOURCE_KIND and ref.id == data.attachment_id and ref.version == data.source_hash), None)
        if reference is None or context.session_id is None:
            raise DlcOperationError(code="WORKBOOK_UNAVAILABLE", message="附件不属于指定会话或版本无效。", status_code=404)
        source = context.resource(reference)
        if not isinstance(source, AttachmentResourceHandle) or source.session_id != context.session_id:
            raise DlcOperationError(code="WORKBOOK_UNAVAILABLE", message="附件不可用。", status_code=404)
        try:
            result = preview(source, data.sheet) if isinstance(data, WorkbookSheetInput) else metadata(source)
            if len(json.dumps({"data": result}, ensure_ascii=False).encode()) > PREVIEW_MAX_BYTES:
                raise ToolInputError("工作表预览表示超过8 MiB限制。")
            return WorkbookViewOutput(data=result)
        except ToolInputError as exc:
            raise DlcOperationError(code="WORKBOOK_PREVIEW_UNAVAILABLE", message=str(exc)[:500], status_code=409) from None

    for name, model, maximum in (("workbooks.metadata", WorkbookViewInput, 32_768), ("workbooks.preview", WorkbookSheetInput, PREVIEW_MAX_BYTES)):
        host.operations.register(DlcOperationSpec(name=name, input_model=model, output_model=WorkbookViewOutput,
                                                 handler=invoke, scope="session", capabilities=("filesystem_read",), max_output_bytes=maximum))
