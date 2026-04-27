#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from xlsx_roster import (
    XlsxRosterError,
    copy_style_from_column,
    ensure_cell,
    find_column,
    find_header_row,
    find_row_by_number,
    load_sheet_document,
    normalize_name,
    normalize_student_id,
    normalize_text,
    read_roster,
    save_sheet_document,
    set_cell_value,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把审阅结果写回学生名单 xlsx。")
    parser.add_argument("--roster", required=True, help="原始学生名单 xlsx")
    parser.add_argument("--review-source", required=True, help="审阅结果 JSON 文件或目录")
    parser.add_argument("--sheet", help="可选，指定工作表名")
    parser.add_argument("--score-column", required=True, help="成绩列名或列字母")
    parser.add_argument("--comment-column", help="评语列名或列字母")
    parser.add_argument("--status-column", help="状态列名或列字母")
    parser.add_argument("--id-column", default="学号", help="学号列表头名或列字母")
    parser.add_argument("--name-column", default="姓名", help="姓名列表头名或列字母")
    parser.add_argument("--allow-missing-ids", action="store_true", help="允许名单中存在无学号学生，并在必要时按姓名回写")
    parser.add_argument("--max-comment-length", type=int, default=60, help="写回评语的最大长度")
    parser.add_argument("--output", help="输出 xlsx 路径；默认生成 *.reviewed.xlsx")
    return parser


def load_review_objects(source: Path) -> list[dict]:
    if source.is_dir():
        items: list[dict] = []
        for json_file in sorted(source.glob("*.json")):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                items.extend(item for item in data if isinstance(item, dict))
            elif isinstance(data, dict):
                items.append(data)
        return items

    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return [item for item in data["results"] if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    raise XlsxRosterError("审阅结果 JSON 格式不支持。")


def normalize_score(value) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError as exc:
        raise XlsxRosterError(f"无法把分数转换为数值：{value}") from exc


def choose_output_path(roster_path: Path, output: str | None) -> Path:
    if output:
        return Path(output)
    return roster_path.with_name(f"{roster_path.stem}.reviewed{roster_path.suffix}")


def main() -> int:
    args = build_parser().parse_args()

    roster_path = Path(args.roster).resolve()
    review_source = Path(args.review_source).resolve()
    if not roster_path.exists():
        raise SystemExit(f"学生名单不存在：{roster_path}")
    if not review_source.exists():
        raise SystemExit(f"审阅结果不存在：{review_source}")

    roster_info = read_roster(
        roster_path,
        sheet_name=args.sheet,
        id_column=args.id_column,
        name_column=args.name_column,
        allow_missing_ids=args.allow_missing_ids,
    )
    doc = load_sheet_document(roster_path, sheet_name=args.sheet)
    header_row_number, headers = find_header_row(doc.sheet_root, doc.shared_strings)
    score_column = find_column(headers, args.score_column)
    comment_column = find_column(headers, args.comment_column) if args.comment_column else None
    status_column = find_column(headers, args.status_column) if args.status_column else None

    score_style = copy_style_from_column(doc.sheet_root, score_column, header_row_number + 1)
    comment_style = (
        copy_style_from_column(doc.sheet_root, comment_column, header_row_number + 1)
        if comment_column
        else None
    )
    status_style = (
        copy_style_from_column(doc.sheet_root, status_column, header_row_number + 1)
        if status_column
        else None
    )

    by_id = {item["student_id"]: item for item in roster_info["students"] if item["student_id"]}
    by_name: dict[str, list[dict]] = {}
    for item in roster_info["students"]:
        if item["student_name"]:
            by_name.setdefault(normalize_name(item["student_name"]), []).append(item)

    updated = 0
    unresolved: list[dict] = []

    for result in load_review_objects(review_source):
        student = None
        student_id = normalize_student_id(result.get("student_id"))
        student_name = normalize_text(result.get("student_name"))
        if student_id and student_id in by_id:
            student = by_id[student_id]
        elif student_name and normalize_name(student_name) in by_name:
            candidates = by_name[normalize_name(student_name)]
            if len(candidates) == 1:
                student = candidates[0]
            else:
                unresolved.append(
                    {
                        "student_id": student_id,
                        "student_name": student_name,
                        "reason": "名单中存在同名学生，无法仅按姓名唯一回写",
                    }
                )
                continue

        if student is None:
            unresolved.append(
                {
                    "student_id": student_id,
                    "student_name": student_name,
                    "reason": "名单中未匹配到该学生",
                }
            )
            continue

        row = find_row_by_number(doc.sheet_root, student["row_number"])
        score_cell = ensure_cell(row, score_column, style_id=score_style)
        set_cell_value(score_cell, normalize_score(result.get("score")))

        if comment_column:
            comment = normalize_text(result.get("comment") or result.get("summary"))
            if len(comment) > args.max_comment_length:
                comment = comment[: args.max_comment_length - 1] + "…"
            comment_cell = ensure_cell(row, comment_column, style_id=comment_style)
            set_cell_value(comment_cell, comment)

        if status_column:
            status_value = normalize_text(result.get("status") or "")
            status_cell = ensure_cell(row, status_column, style_id=status_style)
            set_cell_value(status_cell, status_value)

        updated += 1

    output_path = choose_output_path(roster_path, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_sheet_document(doc, output_path)

    print(json.dumps(
        {
            "output_path": str(output_path),
            "updated_rows": updated,
            "unresolved": unresolved,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
