# 标准化名单 JSON 规范

roster-normalizer 子 agent 必须输出一个 JSON 文件，建议命名为：

```text
roster.normalized.json
```

## 推荐结构

```json
{
  "source_path": "/path/to/raw-roster.pdf",
  "source_type": "pdf",
  "matching_mode_hint": "id_first",
  "needs_manual_review": false,
  "global_notes": [
    "第 3 页较模糊，个别学号可能需要人工复核"
  ],
  "students": [
    {
      "student_id": "示例学号001",
      "student_name": "示例学生甲",
      "gender": "男",
      "class_name": "25级电子信息类",
      "group_name": "",
      "seat_number": "",
      "source_evidence": "PDF 第 2 页第 7 行",
      "confidence": "high",
      "notes": "",
      "needs_manual_review": false
    }
  ]
}
```

## 字段要求

- `source_path`
  - 原始名单路径
- `source_type`
  - 如 `xlsx`、`pdf`、`docx`、`pptx`、`image`
- `matching_mode_hint`
  - `id_first`：名单学号较完整，后续优先用学号匹配
  - `name_first`：名单学号缺失或不稳定，后续优先用姓名匹配
- `needs_manual_review`
  - 只要名单整体质量不稳，就设为 `true`
- `global_notes`
  - 记录整体风险，例如“第 2 页有遮挡”

每个 `students[]` 记录建议包含：

- `student_name`
  - 尽量必填
- `student_id`
  - 学号缺失时可为空字符串
- `gender`
- `class_name`
- `group_name`
- `seat_number`
- `source_evidence`
  - 必填，指向具体页、行、图块
- `confidence`
  - `high` / `medium` / `low`
- `notes`
- `needs_manual_review`

## 识别要求

- 同名学生不要合并
- 不确定的学号不要瞎补
- 页眉、脚注、说明文字不要写进 `students`
- 如果一条记录只有姓名没有学号，也允许保留
- 如果一条记录只有学号没有姓名，允许保留，但要提高复核级别
