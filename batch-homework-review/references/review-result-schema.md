# 审阅结果 JSON 规范

每个子 agent 必须输出一个 JSON 文件，文件名建议为：

```text
reviews/<student_id>.json
```

## 必填字段

```json
{
  "student_id": "示例学号001",
  "student_name": "示例学生甲",
  "submission_paths": [
    "/path/to/submission"
  ],
  "status": "reviewed",
  "score": 86,
  "max_score": 100,
  "summary": "作答完整，核心概念基本正确，但题 3 和题 6 论证偏弱。",
  "comment": "整体完成较好，个别题目论证不够充分。",
  "strengths": [
    "题 1 到题 2 概念回答较完整",
    "能结合例子解释主要思路"
  ],
  "issues": [
    "题 3 缺少关键步骤说明",
    "题 6 没有说明边界情况"
  ],
  "deductions": [
    {
      "points": 8,
      "reason": "题 3 缺少必要步骤"
    },
    {
      "points": 6,
      "reason": "题 6 未处理边界条件"
    }
  ],
  "evidence": [
    "PDF 第 1 页写到了题 1 和题 2 的主要定义",
    "第 2 页题 3 只给结论，没有中间步骤"
  ],
  "needs_manual_review": false
}
```

## 字段说明

- `status`
  - `reviewed`：已完成正常评分
  - `missing`：未找到提交物
  - `ambiguous`：找到多个可疑提交，无法自动归属
  - `unsupported`：提交物格式不支持
  - `manual_review`：看过材料，但无法可靠判分
- `score`
  - 只写数值
  - 若无法评分，可写 `0`，并用 `status` 说明原因
- `comment`
  - 用于回填名单，保持一行短评
  - 建议不超过 `60` 个字
- `summary`
  - 给主 agent 汇总用，可比 `comment` 更完整
- `strengths` / `issues`
  - 每项一句话
  - 保持高信噪比，不要写空话
- `deductions`
  - 每条都必须能落到具体题点
  - `points` 使用正数，表示扣掉的分数
- `evidence`
  - 至少给出 `2` 条
  - 指向具体页、图、文件、函数、题号
- `needs_manual_review`
  - 只要存在“看不清、无法确认、文件损坏、可能识别错人”等情况，就设为
    `true`

## 结果质量要求

- 不要只给总分，不给依据
- 不要只说“完成较好”“一般”，必须指出哪里好、哪里缺
- 不要对没看到的内容做推断
- 如果题目没有总分，统一按 `100` 分制，并在 `summary` 里注明是假设值
