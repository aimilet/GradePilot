#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from xlsx_roster import index_to_col, ns, normalize_student_id, normalize_text

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
X14AC_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DC_TERMS_NS = "http://purl.org/dc/terms/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

ET.register_namespace("", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
ET.register_namespace("r", DOC_REL_NS)
ET.register_namespace("mc", MC_NS)
ET.register_namespace("x14ac", X14AC_NS)
ET.register_namespace("xr", XR_NS)

HEADERS = [
    "序号",
    "学号",
    "姓名",
    "性别",
    "专业/班级",
    "分组",
    "座位",
    "来源证据",
    "置信度",
    "备注",
    "总分",
    "评语",
    "状态",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把标准化名单 JSON 转成可回写的 xlsx。")
    parser.add_argument("--roster-json", required=True, help="标准化名单 JSON 路径")
    parser.add_argument("--output", required=True, help="输出 xlsx 路径")
    parser.add_argument("--sheet-name", default="NormalizedRoster", help="工作表名称")
    return parser


def load_students(json_path: Path) -> list[dict]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get("students"), list):
            return [item for item in data["students"] if isinstance(item, dict)]
        if isinstance(data.get("records"), list):
            return [item for item in data["records"] if isinstance(item, dict)]
        raise SystemExit("名单 JSON 缺少 students 或 records 数组。")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    raise SystemExit("名单 JSON 格式不支持。")


def make_cell(cell_ref: str, value, style: str | None = None) -> ET.Element:
    cell = ET.Element(ns("c"), {"r": cell_ref})
    if style is not None:
        cell.set("s", style)
    if value is None or value == "":
        return cell
    if isinstance(value, (int, float)):
        v_node = ET.SubElement(cell, ns("v"))
        v_node.text = str(value)
        return cell
    cell.set("t", "inlineStr")
    is_node = ET.SubElement(cell, ns("is"))
    text_node = ET.SubElement(is_node, ns("t"))
    text_node.text = str(value)
    return cell


def merge_major_and_class(item: dict) -> str:
    parts = [
        normalize_text(item.get("major")),
        normalize_text(item.get("class_name")),
        normalize_text(item.get("major_or_class")),
    ]
    seen: list[str] = []
    for value in parts:
        if value and value not in seen:
            seen.append(value)
    return " / ".join(seen)


def build_rows(students: list[dict]) -> list[list]:
    rows: list[list] = [HEADERS]
    for index, item in enumerate(students, start=1):
        rows.append(
            [
                index,
                normalize_student_id(item.get("student_id")),
                normalize_text(item.get("student_name")),
                normalize_text(item.get("gender")),
                merge_major_and_class(item),
                normalize_text(item.get("group_name")),
                normalize_text(item.get("seat_number")),
                normalize_text(item.get("source_evidence")),
                normalize_text(item.get("confidence")),
                normalize_text(item.get("notes")),
                normalize_text(item.get("score")),
                normalize_text(item.get("comment")),
                normalize_text(item.get("status")),
            ]
        )
    return rows


def build_sheet_xml(rows: list[list], sheet_name: str) -> bytes:
    root = ET.Element(
        ns("worksheet"),
        {
            f"{{{MC_NS}}}Ignorable": "x14ac xr",
            f"{{{XR_NS}}}uid": "{00000000-0001-0000-0000-000000000000}",
        },
    )
    dimension = ET.SubElement(root, ns("dimension"))
    last_col = index_to_col(len(HEADERS))
    dimension.set("ref", f"A1:{last_col}{len(rows)}")

    sheet_views = ET.SubElement(root, ns("sheetViews"))
    sheet_view = ET.SubElement(sheet_views, ns("sheetView"), {"workbookViewId": "0"})
    selection = ET.SubElement(sheet_view, ns("selection"))
    selection.set("activeCell", "A1")
    selection.set("sqref", "A1")

    ET.SubElement(root, ns("sheetFormatPr"), {f"{{{X14AC_NS}}}dyDescent": "0.25", "defaultRowHeight": "15"})

    cols = ET.SubElement(root, ns("cols"))
    widths = [8, 16, 12, 8, 18, 12, 10, 28, 10, 18, 10, 24, 12]
    for idx, width in enumerate(widths, start=1):
        ET.SubElement(cols, ns("col"), {"min": str(idx), "max": str(idx), "width": str(width), "customWidth": "1"})

    sheet_data = ET.SubElement(root, ns("sheetData"))
    for row_index, values in enumerate(rows, start=1):
        row = ET.SubElement(sheet_data, ns("row"), {"r": str(row_index), f"{{{X14AC_NS}}}dyDescent": "0.25"})
        for col_index, value in enumerate(values, start=1):
            cell_ref = f"{index_to_col(col_index)}{row_index}"
            style = "1" if row_index == 1 else None
            row.append(make_cell(cell_ref, value, style=style))

    ET.SubElement(root, ns("autoFilter"), {"ref": f"A1:{last_col}{len(rows)}"})
    ET.SubElement(root, ns("pageMargins"), {"left": "0.7", "right": "0.7", "top": "0.75", "bottom": "0.75", "header": "0.3", "footer": "0.3"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_styles_xml() -> bytes:
    style_sheet = ET.Element(ns("styleSheet"))

    fonts = ET.SubElement(style_sheet, ns("fonts"), {"count": "2"})
    font1 = ET.SubElement(fonts, ns("font"))
    ET.SubElement(font1, ns("sz"), {"val": "11"})
    ET.SubElement(font1, ns("name"), {"val": "等线"})
    font2 = ET.SubElement(fonts, ns("font"))
    ET.SubElement(font2, ns("b"))
    ET.SubElement(font2, ns("sz"), {"val": "11"})
    ET.SubElement(font2, ns("name"), {"val": "等线"})

    fills = ET.SubElement(style_sheet, ns("fills"), {"count": "3"})
    ET.SubElement(ET.SubElement(fills, ns("fill")), ns("patternFill"), {"patternType": "none"})
    ET.SubElement(ET.SubElement(fills, ns("fill")), ns("patternFill"), {"patternType": "gray125"})
    fill3 = ET.SubElement(fills, ns("fill"))
    pattern = ET.SubElement(fill3, ns("patternFill"), {"patternType": "solid"})
    ET.SubElement(pattern, ns("fgColor"), {"rgb": "FFD9EAF7"})
    ET.SubElement(pattern, ns("bgColor"), {"indexed": "64"})

    borders = ET.SubElement(style_sheet, ns("borders"), {"count": "1"})
    border = ET.SubElement(borders, ns("border"))
    for tag in ["left", "right", "top", "bottom", "diagonal"]:
        ET.SubElement(border, ns(tag))

    cell_style_xfs = ET.SubElement(style_sheet, ns("cellStyleXfs"), {"count": "1"})
    ET.SubElement(cell_style_xfs, ns("xf"), {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0"})

    cell_xfs = ET.SubElement(style_sheet, ns("cellXfs"), {"count": "2"})
    ET.SubElement(cell_xfs, ns("xf"), {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})
    ET.SubElement(cell_xfs, ns("xf"), {"numFmtId": "0", "fontId": "1", "fillId": "2", "borderId": "0", "xfId": "0", "applyFont": "1", "applyFill": "1"})

    cell_styles = ET.SubElement(style_sheet, ns("cellStyles"), {"count": "1"})
    ET.SubElement(cell_styles, ns("cellStyle"), {"name": "Normal", "xfId": "0", "builtinId": "0"})

    return ET.tostring(style_sheet, encoding="utf-8", xml_declaration=True)


def build_workbook_xml(sheet_name: str) -> bytes:
    workbook = ET.Element(ns("workbook"))
    sheets = ET.SubElement(workbook, ns("sheets"))
    ET.SubElement(
        sheets,
        ns("sheet"),
        {
            "name": sheet_name,
            "sheetId": "1",
            f"{{{DOC_REL_NS}}}id": "rId1",
        },
    )
    return ET.tostring(workbook, encoding="utf-8", xml_declaration=True)


def build_workbook_rels_xml() -> bytes:
    root = ET.Element(f"{{{REL_NS}}}Relationships")
    ET.SubElement(root, f"{{{REL_NS}}}Relationship", {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet1.xml"})
    ET.SubElement(root, f"{{{REL_NS}}}Relationship", {"Id": "rId2", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles", "Target": "styles.xml"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_root_rels_xml() -> bytes:
    root = ET.Element(f"{{{REL_NS}}}Relationships")
    ET.SubElement(root, f"{{{REL_NS}}}Relationship", {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "Target": "xl/workbook.xml"})
    ET.SubElement(root, f"{{{REL_NS}}}Relationship", {"Id": "rId2", "Type": "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "Target": "docProps/core.xml"})
    ET.SubElement(root, f"{{{REL_NS}}}Relationship", {"Id": "rId3", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties", "Target": "docProps/app.xml"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_content_types_xml() -> bytes:
    root = ET.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
    ET.SubElement(root, "Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(root, "Default", Extension="xml", ContentType="application/xml")
    ET.SubElement(root, "Override", PartName="/xl/workbook.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
    ET.SubElement(root, "Override", PartName="/xl/worksheets/sheet1.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
    ET.SubElement(root, "Override", PartName="/xl/styles.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml")
    ET.SubElement(root, "Override", PartName="/docProps/core.xml", ContentType="application/vnd.openxmlformats-package.core-properties+xml")
    ET.SubElement(root, "Override", PartName="/docProps/app.xml", ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_app_xml(sheet_name: str) -> bytes:
    xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="{APP_NS}" xmlns:vt="{VT_NS}">
  <Application>Codex</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <HeadingPairs>
    <vt:vector size="2" baseType="variant">
      <vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant>
      <vt:variant><vt:i4>1</vt:i4></vt:variant>
    </vt:vector>
  </HeadingPairs>
  <TitlesOfParts>
    <vt:vector size="1" baseType="lpstr">
      <vt:lpstr>{sheet_name}</vt:lpstr>
    </vt:vector>
  </TitlesOfParts>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>16.0300</AppVersion>
</Properties>
"""
    return xml.encode("utf-8")


def build_core_xml() -> bytes:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="{CP_NS}" xmlns:dc="{DC_NS}" xmlns:dcterms="{DC_TERMS_NS}" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="{XSI_NS}">
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
"""
    return xml.encode("utf-8")


def write_xlsx(output_path: Path, sheet_name: str, rows: list[list]) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", build_content_types_xml())
        archive.writestr("_rels/.rels", build_root_rels_xml())
        archive.writestr("docProps/app.xml", build_app_xml(sheet_name))
        archive.writestr("docProps/core.xml", build_core_xml())
        archive.writestr("xl/workbook.xml", build_workbook_xml(sheet_name))
        archive.writestr("xl/_rels/workbook.xml.rels", build_workbook_rels_xml())
        archive.writestr("xl/styles.xml", build_styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", build_sheet_xml(rows, sheet_name))


def main() -> int:
    args = build_parser().parse_args()
    roster_json = Path(args.roster_json).resolve()
    output = Path(args.output).resolve()
    if not roster_json.exists():
        raise SystemExit(f"名单 JSON 不存在：{roster_json}")

    rows = build_rows(load_students(roster_json))
    output.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx(output, args.sheet_name, rows)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
