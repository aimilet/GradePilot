#!/usr/bin/env python3
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
X14AC_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
NS = {"x": MAIN_NS, "r": REL_NS}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", DOC_REL_NS)
ET.register_namespace("mc", MC_NS)
ET.register_namespace("x14ac", X14AC_NS)
ET.register_namespace("xr", XR_NS)


class XlsxRosterError(RuntimeError):
    """点名册解析或写回失败。"""


@dataclass
class SheetDocument:
    workbook_path: Path
    archive_entries: dict[str, bytes]
    sheet_name: str
    sheet_path: str
    sheet_root: ET.Element
    shared_strings: list[str]


def ns(tag: str) -> str:
    return f"{{{MAIN_NS}}}{tag}"


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\u00a0", "").strip()


def normalize_student_id(value: str | None) -> str:
    return "".join(ch for ch in normalize_text(value) if ch.isdigit())


def normalize_name(value: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(value))


def column_letters(cell_ref: str) -> str:
    match = re.match(r"([A-Z]+)", cell_ref.upper())
    if not match:
        raise XlsxRosterError(f"无法解析单元格列号：{cell_ref}")
    return match.group(1)


def col_to_index(column: str) -> int:
    result = 0
    for char in column.upper():
        if not ("A" <= char <= "Z"):
            raise XlsxRosterError(f"非法列名：{column}")
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result


def index_to_col(index: int) -> str:
    if index <= 0:
        raise XlsxRosterError(f"非法列序号：{index}")
    chars: list[str] = []
    current = index
    while current:
        current, remain = divmod(current - 1, 26)
        chars.append(chr(ord("A") + remain))
    return "".join(reversed(chars))


def parse_shared_strings(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    values: list[str] = []
    for si in root.findall("x:si", NS):
        parts = [text.text or "" for text in si.findall(".//x:t", NS)]
        values.append("".join(parts))
    return values


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//x:t", NS))
    value_node = cell.find("x:v", NS)
    if value_node is None or value_node.text is None:
        return ""
    raw_value = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw_value)]
    if cell_type == "b":
        return "TRUE" if raw_value == "1" else "FALSE"
    return raw_value


def load_sheet_document(workbook_path: str | Path, sheet_name: str | None = None) -> SheetDocument:
    path = Path(workbook_path)
    with zipfile.ZipFile(path) as archive:
        entries = {info.filename: archive.read(info.filename) for info in archive.infolist()}

    workbook_root = ET.fromstring(entries["xl/workbook.xml"])
    workbook_rels = ET.fromstring(entries["xl/_rels/workbook.xml.rels"])
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in workbook_rels.findall("r:Relationship", NS)
    }

    sheets = workbook_root.findall("x:sheets/x:sheet", NS)
    if not sheets:
        raise XlsxRosterError("工作簿中没有工作表。")

    selected_sheet = None
    if sheet_name is None:
        selected_sheet = sheets[0]
    else:
        for sheet in sheets:
            if sheet.attrib.get("name") == sheet_name:
                selected_sheet = sheet
                break
    if selected_sheet is None:
        raise XlsxRosterError(f"未找到工作表：{sheet_name}")

    rel_id = selected_sheet.attrib.get(f"{{http://schemas.openxmlformats.org/officeDocument/2006/relationships}}id")
    if not rel_id or rel_id not in rel_map:
        raise XlsxRosterError("工作表关系缺失，无法定位 sheet XML。")

    target = rel_map[rel_id].lstrip("/")
    sheet_path = target if target.startswith("xl/") else f"xl/{target}"
    shared_strings = []
    if "xl/sharedStrings.xml" in entries:
        shared_strings = parse_shared_strings(entries["xl/sharedStrings.xml"])

    return SheetDocument(
        workbook_path=path,
        archive_entries=entries,
        sheet_name=selected_sheet.attrib["name"],
        sheet_path=sheet_path,
        sheet_root=ET.fromstring(entries[sheet_path]),
        shared_strings=shared_strings,
    )


def iter_rows(sheet_root: ET.Element) -> Iterable[ET.Element]:
    return sheet_root.findall(".//x:sheetData/x:row", NS)


def row_cell_map(row: ET.Element) -> dict[str, ET.Element]:
    mapping: dict[str, ET.Element] = {}
    for cell in row.findall("x:c", NS):
        mapping[column_letters(cell.attrib["r"])] = cell
    return mapping


def find_header_row(
    sheet_root: ET.Element,
    shared_strings: list[str],
    required_headers: tuple[str, str] = ("学号", "姓名"),
    max_scan_rows: int = 20,
) -> tuple[int, dict[str, str]]:
    normalized_required = {normalize_text(item) for item in required_headers}
    for row in iter_rows(sheet_root):
        row_number = int(row.attrib.get("r", "0"))
        if row_number > max_scan_rows:
            break
        headers: dict[str, str] = {}
        values = set()
        for column, cell in row_cell_map(row).items():
            text = normalize_text(cell_value(cell, shared_strings))
            if not text:
                continue
            headers[column] = text
            values.add(text)
        if normalized_required.issubset(values):
            return row_number, headers
    raise XlsxRosterError("未能在前 20 行中定位包含“学号”和“姓名”的表头行。")


def find_column(headers: dict[str, str], column_spec: str) -> str:
    spec = normalize_text(column_spec).upper()
    if re.fullmatch(r"[A-Z]+", spec):
        return spec
    for column, header in headers.items():
        if normalize_text(header).upper() == spec:
            return column
    raise XlsxRosterError(f"未找到目标列：{column_spec}")


def read_roster(
    workbook_path: str | Path,
    sheet_name: str | None = None,
    id_column: str = "学号",
    name_column: str = "姓名",
    allow_missing_ids: bool = False,
) -> dict:
    doc = load_sheet_document(workbook_path, sheet_name=sheet_name)
    header_row_number, headers = find_header_row(doc.sheet_root, doc.shared_strings)
    id_col = find_column(headers, id_column)
    name_col = find_column(headers, name_column)

    students: list[dict] = []
    for row in iter_rows(doc.sheet_root):
        row_number = int(row.attrib.get("r", "0"))
        if row_number <= header_row_number:
            continue
        cells = row_cell_map(row)
        student_id = normalize_student_id(
            cell_value(cells[id_col], doc.shared_strings) if id_col in cells else ""
        )
        student_name = normalize_text(
            cell_value(cells[name_col], doc.shared_strings) if name_col in cells else ""
        )
        if not student_id and not student_name:
            continue
        if not student_id and not allow_missing_ids:
            # 原始点名册底部常有说明文字；默认不接受无学号行。
            continue
        students.append(
            {
                "row_number": row_number,
                "student_id": student_id,
                "student_name": student_name,
            }
        )

    return {
        "sheet_name": doc.sheet_name,
        "header_row_number": header_row_number,
        "headers": headers,
        "students": students,
    }


def find_row_by_number(sheet_root: ET.Element, row_number: int) -> ET.Element:
    for row in iter_rows(sheet_root):
        if int(row.attrib.get("r", "0")) == row_number:
            return row
    raise XlsxRosterError(f"未找到行：{row_number}")


def copy_style_from_column(sheet_root: ET.Element, column: str, start_row_number: int) -> str | None:
    for row in iter_rows(sheet_root):
        row_number = int(row.attrib.get("r", "0"))
        if row_number < start_row_number:
            continue
        cell = row_cell_map(row).get(column)
        if cell is not None and "s" in cell.attrib:
            return cell.attrib["s"]
    return None


def ensure_cell(row: ET.Element, column: str, style_id: str | None = None) -> ET.Element:
    row_number = int(row.attrib.get("r", "0"))
    target_ref = f"{column}{row_number}"
    cells = row.findall("x:c", NS)
    for cell in cells:
        if cell.attrib.get("r") == target_ref:
            return cell

    new_cell = ET.Element(ns("c"), {"r": target_ref})
    if style_id is not None:
        new_cell.set("s", style_id)

    target_index = col_to_index(column)
    inserted = False
    for index, cell in enumerate(cells):
        current_column = column_letters(cell.attrib["r"])
        if col_to_index(current_column) > target_index:
            row.insert(index, new_cell)
            inserted = True
            break
    if not inserted:
        row.append(new_cell)
    return new_cell


def _clear_cell_children(cell: ET.Element) -> None:
    for child in list(cell):
        cell.remove(child)


def set_cell_value(cell: ET.Element, value: str | int | float | None) -> None:
    _clear_cell_children(cell)
    if value is None or value == "":
        cell.attrib.pop("t", None)
        return

    if isinstance(value, (int, float)):
        cell.attrib.pop("t", None)
        node = ET.SubElement(cell, ns("v"))
        node.text = str(value)
        return

    cell.set("t", "inlineStr")
    is_node = ET.SubElement(cell, ns("is"))
    text_node = ET.SubElement(is_node, ns("t"))
    if value[:1].isspace() or value[-1:].isspace():
        text_node.set(XML_SPACE, "preserve")
    text_node.text = value


def save_sheet_document(doc: SheetDocument, output_path: str | Path) -> Path:
    output = Path(output_path)
    invalid_uid_key = f"{{{X14AC_NS}}}uid"
    valid_uid_key = f"{{{XR_NS}}}uid"
    if invalid_uid_key in doc.sheet_root.attrib and valid_uid_key not in doc.sheet_root.attrib:
        doc.sheet_root.attrib[valid_uid_key] = doc.sheet_root.attrib.pop(invalid_uid_key)
        ignorable_key = f"{{{MC_NS}}}Ignorable"
        ignorable = doc.sheet_root.attrib.get(ignorable_key, "")
        tokens = [token for token in ignorable.split() if token]
        if "x14ac" not in tokens:
            tokens.append("x14ac")
        if "xr" not in tokens:
            tokens.append("xr")
        doc.sheet_root.attrib[ignorable_key] = " ".join(tokens)

    updated_entries = dict(doc.archive_entries)
    updated_entries[doc.sheet_path] = ET.tostring(
        doc.sheet_root,
        encoding="utf-8",
        xml_declaration=True,
    )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in updated_entries.items():
            archive.writestr(name, content)
    return output
