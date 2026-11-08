"""Bounded XLSX reading and immutable relational preparation owned by Data."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from io import BytesIO
from pathlib import PurePosixPath
import re
import time
from uuid import uuid4
import zipfile

from defusedxml.ElementTree import iterparse
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter, range_boundaries
from dbfox_dlc_api import AttachmentResourceHandle, ToolInputError

from .contracts import WorkbookColumn, WorkbookDatabaseHandle, WorkbookRegion, WorkbookSource
from .store import DataStateStore
from .sensitivity import is_sensitive_name

MAX_ROWS = 100_000
MAX_COLUMNS = 128
MAX_CELLS = 1_000_000
MAX_SHEETS = 20
MAX_ZIP_BYTES = 100 * 1024 * 1024
PARSER_VERSION = "xlsx-2"
MAX_REGIONS = 24
INSPECT_MAX_BYTES = 24_000


def _bounds(value: str) -> tuple[int, int, int, int]:
    # Use openpyxl for address parsing, while excluding whole-column/row and
    # cross-sheet references at this single-sheet capability boundary.
    if not re.fullmatch(r"\$?[A-Za-z]{1,3}\$?[1-9]\d*(?::\$?[A-Za-z]{1,3}\$?[1-9]\d*)?", value):
        raise ToolInputError("请使用明确的单工作表单元格范围，例如A4:E13。")
    left, top, right, bottom = range_boundaries(value)
    if not (1 <= left <= right <= MAX_COLUMNS and 1 <= top <= bottom <= MAX_ROWS + 1):
        raise ToolInputError("单元格范围无效或超过100,001行、128列的处理边界。")
    return left, top, right, bottom


def _address(bounds: tuple[int, int, int, int]) -> str:
    left, top, right, bottom = bounds
    return f"{get_column_letter(left)}{top}:{get_column_letter(right)}{bottom}"


def _field_name(name: str) -> bool:
    return bool(name and len(name) <= 256 and not name.startswith("__") and not any(ord(c) < 32 for c in name))


def checkpoint(cancelled: Callable[[], bool], deadline: float) -> None:
    if cancelled() or time.monotonic() > deadline:
        raise ToolInputError("工作簿处理已取消或超过60秒，请缩小文件后重试。")


def preflight(source: AttachmentResourceHandle, cancelled: Callable[[], bool], deadline: float) -> dict[str, dict[str, int]]:
    """Validate the container/XML before openpyxl; never extract ZIP paths."""
    if not source.display_name.lower().endswith(".xlsx"):
        raise ToolInputError("第一版仅支持.xlsx工作簿。")
    if not source.path.is_file() or hashlib.sha256(source.path.read_bytes()).hexdigest() != source.content_sha256:
        raise ToolInputError("原始附件缺失或完整性检查失败。")
    statistics = {}
    try:
        with zipfile.ZipFile(source.path) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) > 10_000 or len(names) != len(set(names)):
                raise ToolInputError("工作簿包含过多或重复的ZIP条目。")
            if "xl/workbook.xml" not in names or any("vbaproject" in n.lower() for n in names):
                raise ToolInputError("文件不是受支持的无宏.xlsx工作簿。")
            total = 0
            for entry in entries:
                checkpoint(cancelled, deadline)
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or entry.flag_bits & 1:
                    raise ToolInputError("工作簿容器路径或加密方式不受支持。")
                if entry.file_size > MAX_ZIP_BYTES:
                    raise ToolInputError("工作簿解压后超过100 MiB限制。")
                with archive.open(entry) as stream:
                    while chunk := stream.read(65_536):
                        total += len(chunk)
                        checkpoint(cancelled, deadline)
                        if total > MAX_ZIP_BYTES:
                            raise ToolInputError("工作簿解压后超过100 MiB限制。")
                # Security preflight only. Cell values/types are read by openpyxl.
                if entry.filename.endswith(".xml"):
                    stats = {"rows": 0, "columns": 0, "cells": 0, "hidden_rows": 0, "merged_cells": 0}
                    with archive.open(entry) as stream:
                        depth, nodes = 0, 0
                        for event, element in iterparse(stream, events=("start", "end"), forbid_dtd=True):
                            if event == "start":
                                depth += 1
                                nodes += 1
                                if depth > 256 or nodes > 5_000_000:
                                    raise ToolInputError("工作簿XML结构超过解析预算。")
                                if nodes % 1024 == 0:
                                    checkpoint(cancelled, deadline)
                                continue
                            tag = element.tag.rsplit("}", 1)[-1]
                            if tag == "c" and "/worksheets/" in entry.filename:
                                stats["cells"] += 1
                                if stats["cells"] > MAX_CELLS:
                                    raise ToolInputError("单个工作表超过100万个单元格限制。")
                                row, column = coordinate_to_tuple(element.attrib.get("r", "A1"))
                                stats["rows"] = max(stats["rows"], row)
                                stats["columns"] = max(stats["columns"], column)
                            elif tag == "row" and element.attrib.get("hidden") == "1":
                                stats["hidden_rows"] += 1
                            elif tag == "mergeCell" and "/worksheets/" in entry.filename:
                                left, top, right, bottom = range_boundaries(element.attrib["ref"])
                                stats["merged_cells"] += (right - left + 1) * (bottom - top + 1)
                                if stats["merged_cells"] > MAX_CELLS:
                                    raise ToolInputError("工作表合并区域超过解析预算。")
                            element.clear()
                            depth -= 1
                    if "/worksheets/" in entry.filename:
                        statistics[entry.filename] = stats
            if len(statistics) > MAX_SHEETS:
                raise ToolInputError("工作簿不能超过20个工作表。")
    except ToolInputError:
        raise
    except Exception as exc:
        raise ToolInputError("无法读取工作簿：文件损坏、加密或XML结构不受支持。") from exc
    return statistics


def _cell_value(cell, *, text: bool = False):
    value = cell.value
    if text and isinstance(value, (int, float)) and not isinstance(value, bool):
        if re.fullmatch(r"0+", cell.number_format or "") and float(value).is_integer():
            return str(int(value)).zfill(len(cell.number_format))
        if float(value).is_integer():
            return str(int(value))
    return value


def _kind(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, (int, float, Decimal)):
        return "decimal"
    return "text"


def _json_value(value):
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    return value


def _decimal(value, row: int, column: str) -> Decimal:
    try:
        if isinstance(value, bool) or (isinstance(value, str) and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value.strip()) is None):
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or len(result.as_tuple().digits) > 38 or result.adjusted() > 37:
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        raise ToolInputError(f"第{row}行「{column}」不是可可靠计算的数值；请澄清或明确排除该行。") from None


class WorkbookService:
    def __init__(self, store: DataStateStore):
        self.store = store

    def inspect(self, source: AttachmentResourceHandle, *, sheet: str | None = None,
                cell_range: str | None = None, cancelled: Callable[[], bool] = lambda: False) -> dict:
        deadline = time.monotonic() + 60
        stats = preflight(source, cancelled, deadline)
        workbook = load_workbook(BytesIO(source.path.read_bytes()), read_only=True, data_only=False, keep_links=False)
        try:
            visible = [ws for ws in workbook if ws.sheet_state == "visible"]
            if sheet is not None and sheet not in workbook.sheetnames:
                raise ToolInputError("指定工作表不存在，请使用检视返回的完整名称。")
            chosen = workbook[sheet] if sheet else visible[0] if len(visible) == 1 else None
            if cell_range is not None and chosen is None:
                raise ToolInputError("检视单元格范围前，请先指定工作表的完整名称。")
            result = {"attachment_id": source.id, "content_sha256": source.content_sha256,
                      "sheets": [{"name": ws.title, "state": ws.sheet_state,
                                  **stats.get(ws._worksheet_path, {})} for ws in workbook],
                      "full_data_scanned": False, "table": None,
                      "warnings": ["检视样本不代表全量统计；分析包括隐藏行和筛选隐藏的明细。公式不重算，计算涉及公式列时需要值副本。"]}
            if chosen is not None:
                if chosen.sheet_state != "visible":
                    raise ToolInputError("第一版分析仅支持可见工作表。")
                extent = stats[chosen._worksheet_path]
                bounds = _bounds(cell_range) if cell_range else (1, 1, max(1, min(extent["columns"], 8)), max(1, min(extent["rows"], 32)))
                left, top, right, bottom = bounds
                if bottom - top >= 64 or right - left >= 16:
                    raise ToolInputError("每次最多检视64行、16列，请缩小cell_range后分段读取。")
                if top > max(1, extent["rows"]) or left > max(1, extent["columns"]):
                    raise ToolInputError("检视范围位于工作表实际数据边界之外。")
                chosen.reset_dimensions()
                samples: list[dict[str, object]] = []
                candidates: list[dict[str, object]] = []
                sensitive_positions: set[int] = set()
                table = {"sheet": chosen.title, "cell_range": _address(bounds), "first_column": left,
                         "candidate_headers": candidates, "samples": samples,
                         "scanned_through_row": top - 1, "next_range": None}
                result["table"] = table
                # Start at row 1 to retain sensitivity labels above a later page.
                # No unbounded data rows enter the response or durable facts.
                for row_number, row in enumerate(chosen.iter_rows(min_row=1, max_row=bottom, max_col=right), 1):
                    checkpoint(cancelled, deadline)
                    values = [_cell_value(c) for c in row]
                    fields = [(i, v.strip()) for i, v in enumerate(values) if isinstance(v, str) and _field_name(v.strip()) and not v.startswith("=")]
                    sensitive_positions.update(i for i, value in fields if is_sensitive_name(value))
                    if row_number < top:
                        continue
                    window = values[left - 1:right]
                    populated = [v for v in window if v is not None]
                    candidate = None
                    if (len(candidates) < 8 and len(populated) >= 2
                            and all(isinstance(v, str) and _field_name(v.strip()) and not v.startswith("=") for v in populated)
                            and len(populated) == len({v.strip().casefold() for v in populated})):
                        candidate = {"row": row_number, "headers": [
                            "[REDACTED]" if i + left - 1 in sensitive_positions and v is not None and not is_sensitive_name(str(v))
                            else str(v)[:80] if v is not None else None for i, v in enumerate(window)],
                                     "columns": [f"{get_column_letter(i + left)}{row_number}" for i, v in enumerate(window) if v is not None]}
                        candidates.append(candidate)
                    if populated:
                        samples.append({"row": row_number, "values": [
                            "[REDACTED]" if i + left - 1 in sensitive_positions and v is not None and not is_sensitive_name(str(v))
                            else str(_json_value(v))[:120] if v is not None else None
                            for i, v in enumerate(window)
                        ], "truncated_columns": [get_column_letter(i + left) for i, v in enumerate(window) if v is not None and len(str(_json_value(v))) > 120]})
                    if len(json.dumps(result, ensure_ascii=False).encode()) > INSPECT_MAX_BYTES:
                        if populated:
                            samples.pop()
                        if candidate is not None:
                            candidates.pop()
                        break
                    table["scanned_through_row"] = row_number
                scanned = table["scanned_through_row"]
                if scanned < extent["rows"]:
                    table["next_range"] = _address((left, scanned + 1, right, min(scanned + bottom - top + 1, extent["rows"])))
            return result
        finally:
            workbook.close()

    def prepare(self, source: AttachmentResourceHandle, *, project_id: str, sheet: str, header_row: int,
                columns: list[str] | None = None, column_types: dict[str, str] | None = None,
                exclude_rows: dict[int, str] | None = None, regions: list[WorkbookRegion] | None = None,
                cancelled: Callable[[], bool] = lambda: False) -> WorkbookDatabaseHandle:
        import duckdb
        deadline = time.monotonic() + 60
        if not 1 <= header_row <= MAX_ROWS + 1:
            raise ToolInputError("表头行超出处理边界。")
        if regions is not None and not 1 <= len(regions) <= MAX_REGIONS:
            raise ToolInputError("请指定1至24个明确的明细区块。")
        regions = [r.model_copy(update={"data_range": _address(_bounds(r.data_range))}) for r in regions] if regions is not None else None
        specs = {"parser": PARSER_VERSION, "sheet": sheet, "header_row": header_row,
                 "columns": columns, "column_types": column_types or {}, "exclude_rows": exclude_rows or {},
                 "regions": [r.model_dump(mode="json") for r in regions] if regions is not None else None}
        recipe = hashlib.sha256(json.dumps({"session": source.session_id, "source": source.id, "hash": source.content_sha256, **specs}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        dataset_id = "wb_" + recipe[:32]
        existing = self.store.get_workbook(dataset_id)
        if existing is not None:
            try:
                self.store.check_workbook_files(existing)
            except ValueError:
                # Rebuildable derived storage; preflight below still requires
                # the exact intact original, never a different reader/file.
                pass
            else:
                return existing
        statistics = preflight(source, cancelled, deadline)
        workbook = load_workbook(BytesIO(source.path.read_bytes()), read_only=True, data_only=False, keep_links=False)
        try:
            if sheet not in workbook.sheetnames or workbook[sheet].sheet_state != "visible":
                raise ToolInputError("指定工作表不存在或不可见，请重新确认。")
            ws = workbook[sheet]
            stats = statistics[ws._worksheet_path]
            if stats["rows"] > MAX_ROWS + 1 or stats["columns"] > MAX_COLUMNS or stats["cells"] > MAX_CELLS:
                raise ToolInputError("选定工作表超过10万明细行、128列或100万单元格限制；未进行部分计算。")
            if header_row >= stats["rows"]:
                raise ToolInputError("表头之后没有可分析的明细行。")
            ws.reset_dimensions()
            width = stats["columns"]
            headers = next(ws.iter_rows(min_row=header_row, max_row=header_row, max_col=width))
            names = [c.value.strip() if isinstance(c.value, str) and c.data_type != "f" else "" for c in headers]
            last_named = max((i + 1 for i, name in enumerate(names) if name), default=0)
            selected = list(columns) if columns is not None else names[:last_named]
            if not selected or any(not _field_name(n) for n in selected) or len(selected) != len({n.casefold() for n in selected}):
                raise ToolInputError("所选表头包含空白、重复或保留字段名，请明确选择单层唯一的文本字段。")
            if any(names.count(name) != 1 or sum(n.casefold() == name.casefold() for n in names) != 1 for name in selected):
                raise ToolInputError("选择的列不存在、重复或为空。")
            if any(c not in selected for c in (column_types or {})):
                raise ToolInputError("列类型声明必须属于本次选择的字段。")
            if any(t not in ("text", "decimal", "integer", "date", "datetime", "boolean") for t in (column_types or {}).values()):
                raise ToolInputError("不支持指定的字段类型。")
            positions = [names.index(name) for name in selected]
            selected_regions = sorted(regions or [WorkbookRegion(data_range=_address((1, header_row + 1, width, stats["rows"])))],
                                      key=lambda r: _bounds(r.data_range)[1])
            region_bounds = [_bounds(r.data_range) for r in selected_regions]
            context_names = sorted(selected_regions[0].context_cells)
            if any(not _field_name(n) or n.casefold() in {c.casefold() for c in selected} for n in context_names) or len(context_names) != len({n.casefold() for n in context_names}):
                raise ToolInputError("区块上下文字段名无效或与明细字段重复。")
            for i, (region, (left, top, right, bottom)) in enumerate(zip(selected_regions, region_bounds)):
                if top <= header_row or bottom > stats["rows"] or right > width or any(not left <= p + 1 <= right for p in positions):
                    raise ToolInputError("明细区块必须位于表头之后、实际数据边界内，并包含全部所选字段。")
                if i and top <= region_bounds[i - 1][3]:
                    raise ToolInputError("明细区块行号不能重叠，避免重复计算。")
                if sorted(region.context_cells) != context_names:
                    raise ToolInputError("所有区块必须使用相同的上下文字段名。")
            context_addresses = set()
            for region in selected_regions:
                for address in region.context_cells.values():
                    left, top, right, bottom = _bounds(address)
                    if left != right or top != bottom or top > stats["rows"] or left > width:
                        raise ToolInputError("区块上下文必须引用同一工作表中实际存在的单个文本单元格。")
                    context_addresses.add((top, left))
            records = []
            kinds: list[set[str]] = [set() for _ in selected]
            excluded, seen_exclusions = exclude_rows or {}, set()
            if any(not isinstance(r, int) or not isinstance(reason, str) or not reason.strip() or len(reason) > 200 for r, reason in excluded.items()):
                raise ToolInputError("排除行必须包含原始行号和明确原因。")
            currency_positions = {i: name for i, name in enumerate(names) if name and re.search(r"币种|货币|currency", name, re.I)}
            currencies: dict[str, set[str]] = {name: set() for name in currency_positions.values()}
            context_values, record_regions, unselected_count, region_index = {}, [], 0, 0
            for row_number, cells in enumerate(ws.iter_rows(min_row=1, max_row=stats["rows"], max_col=width), 1):
                checkpoint(cancelled, deadline)
                for row, col in context_addresses:
                    if row_number == row:
                        cell = cells[col - 1]
                        if cell.data_type in ("f", "e") or not isinstance(cell.value, str) or not cell.value.strip() or len(cell.value) > 32_767:
                            raise ToolInputError(f"区块上下文{get_column_letter(col)}{row}必须是非空文本，不能使用公式或错误值。")
                        context_values[(row, col)] = cell.value
                while region_index < len(region_bounds) and row_number > region_bounds[region_index][3]:
                    region_index += 1
                inside = region_index < len(region_bounds) and region_bounds[region_index][1] <= row_number <= region_bounds[region_index][3]
                if not inside:
                    if row_number != header_row and any(c.value is not None for c in cells):
                        unselected_count += 1
                    continue
                if row_number in excluded:
                    left, _top, right, _bottom = region_bounds[region_index]
                    if all(c.value is None for c in cells[left - 1:right]):
                        raise ToolInputError("排除行必须是所选区块中的实际明细行。")
                    seen_exclusions.add(row_number)
                    continue
                if columns is None and any(c.value is not None for c in cells[last_named:]):
                    raise ToolInputError("空白表头列含数据，请明确选择需要的字段，不能自动忽略。")
                left, _top, right, _bottom = region_bounds[region_index]
                if all(c.value is None for c in cells[left - 1:right]):
                    continue
                if all(isinstance(cells[p].value, str) and cells[p].value.strip() == name for p, name in zip(positions, selected)):
                    raise ToolInputError(f"第{row_number}行是重复表头，请使用regions指定真实明细范围。")
                if any(str(c.value).strip().casefold() in ("合计", "总计", "小计", "grand total") for c in cells[left - 1:min(right, left + 3)]):
                    raise ToolInputError(f"第{row_number}行疑似汇总行，请明确排除后再准备明细。")
                for position, name in currency_positions.items():
                    value = cells[position].value
                    currencies[name].add(str(value).strip()[:80] if value is not None else "[缺失]")
                    if len(currencies[name]) > 20:
                        raise ToolInputError(f"「{name}」包含超过20种货币标识，请确认字段和统计口径。")
                values = []
                for i, position in enumerate(positions):
                    cell = cells[position]
                    if cell.data_type == "f":
                        raise ToolInputError(f"第{row_number}行「{selected[i]}」包含公式；首版计算需要值副本，不使用可能过期的缓存。")
                    if cell.data_type == "e":
                        raise ToolInputError(f"第{row_number}行「{selected[i]}」包含Excel错误值。")
                    as_text = (column_types or {}).get(selected[i]) == "text" or bool(re.search(r"编码|代码|订单号|商品号|编号|(?:^|_)id$|code", selected[i], re.I))
                    value = _cell_value(cell, text=as_text)
                    if value is not None:
                        if isinstance(value, str) and len(value) > 32_767:
                            raise ToolInputError("单元格文本超过Excel支持范围。")
                        kinds[i].add("text" if as_text else _kind(value))
                    values.append(str(value) if value is not None and as_text else value)
                records.append((row_number, values))
                record_regions.append(region_index)
            if set(excluded) != seen_exclusions:
                raise ToolInputError("排除行必须是选定工作表中实际存在的明细行。")
            if not records:
                raise ToolInputError("选定工作表没有可分析的明细行。")
            types = []
            for index, name in enumerate(selected):
                declared = (column_types or {}).get(name)
                detected = kinds[index]
                if not declared and len(detected) > 1 and not detected <= {"date", "datetime"}:
                    raise ToolInputError(f"「{name}」包含混合类型，请明确字段类型或数据问题的处理方式。")
                kind = declared or ("datetime" if "datetime" in detected else next(iter(detected), "text"))
                numeric_values: list[Decimal] = []
                for row_number, row_values in records:
                    value = row_values[index]
                    if value is None and kind in ("decimal", "integer"):
                        raise ToolInputError(f"第{row_number}行「{name}」缺少必要值，请澄清或明确排除。")
                    if kind in ("decimal", "integer"):
                        number = _decimal(value, row_number, name)
                        if kind == "integer" and number != number.to_integral_value():
                            raise ToolInputError(f"第{row_number}行「{name}」不是整数。")
                        numeric_values.append(number)
                        value = number
                    elif kind in ("date", "datetime") and value is not None:
                        if isinstance(value, str):
                            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?", value):
                                raise ToolInputError(f"第{row_number}行「{name}」的文本日期有歧义，请提供明确日期值。")
                            try:
                                value = datetime.fromisoformat(value)
                            except ValueError:
                                raise ToolInputError(f"第{row_number}行「{name}」的日期无效。") from None
                        if not isinstance(value, (date, datetime)):
                            raise ToolInputError(f"第{row_number}行「{name}」不是有效日期。")
                    elif kind == "text" and value is not None:
                        value = str(value)
                    elif kind == "boolean" and value is not None and not isinstance(value, bool):
                        raise ToolInputError(f"第{row_number}行「{name}」不是明确的布尔值。")
                    row_values[index] = value
                if kind in ("decimal", "integer"):
                    # _decimal has already rejected non-finite exponents.
                    scale = max(max(-int(v.as_tuple().exponent), 0) for v in numeric_values)
                    integer_digits = max(max(v.adjusted() + 1, 1) for v in numeric_values)
                    if scale + integer_digits > 38:
                        raise ToolInputError(f"「{name}」超出DECIMAL的精度范围。")
                    sql_type = f"DECIMAL(38,{scale})"
                else:
                    sql_type = {"text": "VARCHAR", "boolean": "BOOLEAN", "date": "DATE", "datetime": "TIMESTAMP"}[kind]
                types.append(WorkbookColumn(name=name, type=sql_type, source_column=positions[index] + 1))
            for (_row_number, values), index in zip(records, record_regions):
                region = selected_regions[index]
                for name in context_names:
                    left, top, _right, _bottom = _bounds(region.context_cells[name])
                    values.append(context_values[(top, left)])
            types.extend(WorkbookColumn(name=name, type="VARCHAR", source_column=None) for name in context_names)
        finally:
            workbook.close()
        root = self.store.database_path.parent / "workbooks"
        root.mkdir(parents=True, exist_ok=True)
        final = root / (dataset_id + ".duckdb")
        temporary = root / (dataset_id + "." + uuid4().hex + ".tmp")
        connection = None
        try:
            connection = duckdb.connect(str(temporary), config={"enable_external_access": False, "threads": 1, "memory_limit": "128MB"})
            connection.execute("BEGIN TRANSACTION")
            quoted = lambda value: '"' + value.replace('"', '""') + '"'
            connection.execute("CREATE TABLE data (" + ", ".join(quoted(c.name) + " " + c.type for c in types) + ", __source_row BIGINT NOT NULL)")
            placeholders = ",".join("?" for _ in range(len(types) + 1))
            for offset in range(0, len(records), 1000):
                checkpoint(cancelled, deadline)
                connection.executemany("INSERT INTO data VALUES (" + placeholders + ")", [values + [row] for row, values in records[offset:offset + 1000]])
            connection.execute("COMMIT")
            connection.execute("CHECKPOINT")
            connection.close()
            connection = None
            checkpoint(cancelled, deadline)
            handle = WorkbookDatabaseHandle(
                id=dataset_id, scope_version=recipe, project_id=project_id, session_id=source.session_id,
                display_name=source.display_name + " / " + sheet, path=final, source_path=source.path,
                file_sha256=hashlib.sha256(temporary.read_bytes()).hexdigest(),
                source=WorkbookSource(attachment_id=source.id, content_sha256=source.content_sha256, sheet=sheet, header_row=header_row, excluded_rows=excluded,
                                      regions=tuple(selected_regions), unselected_nonempty_rows=unselected_count,
                                      currency_values={name: tuple(sorted(values)) for name, values in currencies.items()},
                                      null_counts={name: sum(values[index] is None for _row, values in records) for index, name in enumerate(selected) if any(values[index] is None for _row, values in records)}),
                columns=tuple(types), row_count=len(records), created_at=datetime.now(UTC).isoformat(),
            )
            return self.store.publish_workbook(handle, temporary)
        finally:
            if connection is not None:
                connection.close()
            temporary.unlink(missing_ok=True)
