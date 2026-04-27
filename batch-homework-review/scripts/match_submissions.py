#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from xlsx_roster import normalize_name, read_roster


IGNORE_NAMES = {
    ".ds_store",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="按学号/姓名匹配学生名单与提交物。")
    parser.add_argument("--roster", required=True, help="学生名单 xlsx 路径")
    parser.add_argument("--submissions-dir", required=True, help="学生作业目录")
    parser.add_argument("--sheet", help="可选，指定工作表名")
    parser.add_argument("--allow-missing-ids", action="store_true", help="允许名单中存在无学号学生，并退化为按姓名匹配")
    parser.add_argument("--output", help="输出 JSON 路径；不填则打印到标准输出")
    return parser


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def normalize_label(path: Path) -> tuple[str, str]:
    text = path.name.replace("\u00a0", "")
    compact = "".join(text.split()).lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    return compact, digits


def collect_candidates(submissions_dir: Path) -> list[Path]:
    top_level_dirs: list[Path] = []
    for child in sorted(submissions_dir.iterdir()):
        if is_hidden(child) or child.name.lower() in IGNORE_NAMES:
            continue
        if child.is_dir():
            top_level_dirs.append(child)

    candidates: list[Path] = list(top_level_dirs)
    for file_path in sorted(submissions_dir.rglob("*")):
        if is_hidden(file_path) or file_path.name.lower() in IGNORE_NAMES:
            continue
        if file_path.is_dir():
            continue
        candidates.append(file_path)
    return candidates


def main() -> int:
    args = build_parser().parse_args()

    submissions_dir = Path(args.submissions_dir).resolve()
    roster_path = Path(args.roster).resolve()
    if not submissions_dir.is_dir():
        raise SystemExit(f"作业目录不存在：{submissions_dir}")

    roster = read_roster(args.roster, sheet_name=args.sheet, allow_missing_ids=args.allow_missing_ids)
    students = roster["students"]

    by_id = {item["student_id"]: item for item in students if item["student_id"]}
    by_name: dict[str, list[dict]] = {}
    for item in students:
        if item["student_name"]:
            by_name.setdefault(normalize_name(item["student_name"]), []).append(item)

    def student_key(item: dict) -> str:
        if item["student_id"]:
            return item["student_id"]
        return f"name:{normalize_name(item['student_name'])}:row:{item['row_number']}"

    def unique_students(items: list[dict]) -> list[dict]:
        seen: set[tuple[str, int]] = set()
        result: list[dict] = []
        for item in items:
            key = (item.get("student_id", ""), item["row_number"])
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    results = {
        "sheet_name": roster["sheet_name"],
        "header_row_number": roster["header_row_number"],
        "summary": {
            "total_students": len(students),
            "matched_students": 0,
            "unmatched_students": 0,
            "unmatched_files": 0,
            "ambiguous_files": 0,
        },
        "students": [],
        "unmatched_students": [],
        "unmatched_files": [],
        "ambiguous_files": [],
    }

    student_map = {
        student_key(item): {
            "student_id": item["student_id"],
            "student_name": item["student_name"],
            "row_number": item["row_number"],
            "matched_paths": [],
            "match_basis": [],
        }
        for item in students
    }

    claimed_dirs: set[Path] = set()
    for candidate in collect_candidates(submissions_dir):
        if candidate.resolve() == roster_path:
            continue
        if any(root in candidate.resolve().parents for root in claimed_dirs):
            continue
        compact_label, digits_label = normalize_label(candidate)
        id_matches = [
            student
            for student_id, student in by_id.items()
            if student_id and student_id in digits_label
        ]
        name_matches = [
            student
            for student_name, students_by_name in by_name.items()
            if student_name and student_name in compact_label
            for student in students_by_name
        ]

        matches = unique_students(id_matches or name_matches)
        basis = "student_id" if id_matches else "student_name" if name_matches else None

        if len(matches) == 1:
            key = student_key(matches[0])
            student_map[key]["matched_paths"].append(str(candidate))
            student_map[key]["match_basis"].append(basis)
            if candidate.is_dir():
                claimed_dirs.add(candidate.resolve())
        elif len(matches) > 1:
            results["ambiguous_files"].append(
                {
                    "path": str(candidate),
                    "matched_students": [
                        {
                            "student_id": item["student_id"],
                            "student_name": item["student_name"],
                        }
                        for item in matches
                    ],
                }
            )
        else:
            results["unmatched_files"].append(str(candidate))

    for item in student_map.values():
        entry = {
            "student_id": item["student_id"],
            "student_name": item["student_name"],
            "row_number": item["row_number"],
            "matched_paths": sorted(set(item["matched_paths"])),
            "match_basis": sorted(set(filter(None, item["match_basis"]))),
        }
        if entry["matched_paths"]:
            results["students"].append(entry)
        else:
            results["unmatched_students"].append(
                {
                    "student_id": entry["student_id"],
                    "student_name": entry["student_name"],
                    "row_number": entry["row_number"],
                }
            )

    results["students"].sort(key=lambda item: item["row_number"])
    results["unmatched_students"].sort(key=lambda item: item["row_number"])
    results["summary"]["matched_students"] = len(results["students"])
    results["summary"]["unmatched_students"] = len(results["unmatched_students"])
    results["summary"]["unmatched_files"] = len(results["unmatched_files"])
    results["summary"]["ambiguous_files"] = len(results["ambiguous_files"])

    payload = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
        print(output_path)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
