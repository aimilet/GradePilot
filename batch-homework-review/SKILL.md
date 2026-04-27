---
name: batch-homework-review
description: 批量审阅学生作业并并行调度多个子 agent，对照题目文件为每个学生评分、抽取证据、处理 pdf、pptx、docx、图片、压缩包 等提交物，并将结果回写学生名单。支持先把图片、pdf、docx、pptx、非标准 xlsx 等名单识别为标准化名单，再生成专用 xlsx 用于后续匹配和回写。用户明确提供作业目录、题目位置、学生名单位置、成绩列或备注列，或要求批量批改、批量评分、回写点名册/名单时使用。
---

# Batch Homework Review

按“名单标准化 -> 题目基线 -> 提交物匹配 -> 分批并行审阅 -> 汇总结果 -> 回写名单”的顺序执行。

## 输入约定

在开始前收紧这些输入；缺失时先补齐，再进入批量审阅：

- `submissions_dir`：学生作业目录
- `assignment_path`：题目文件或题目目录
- `roster_path`：学生名单，可以是 `.xlsx/.pdf/.docx/.pptx/.jpg/.png`
- `score_column`：写回成绩的列名或列字母，例如 `8`、`F`
- `comment_column`：可选，写回简短评语的列名或列字母，例如 `备注`、`G`
- `status_column`：可选，写回状态，如 `已审阅` / `人工复核`
- `batch_size`：默认 `3` 或 `4`
- `max_score`：题目未显式给出总分时，默认 `100`

先在作业目录旁创建一次运行目录，例如：

```text
_review_runs/20260427-153000/
  roster.normalized.json
  roster.normalized.xlsx
  manifest.json
  reviews/
  extracted/
```

把每个子 agent 的结果写入 `reviews/<student_id>.json`。结果格式见
`references/review-result-schema.md`。

如果需要直接复制可执行的提示词，读取
`references/agent-prompts.md`。

如果使用本 skill 生成的标准化名单 xlsx，默认回写列可直接用：

- `score_column=总分`
- `comment_column=评语`
- `status_column=状态`

## 主流程

### 0. 标准化学生名单

如果名单不是“表头清晰、可直接回写的标准 xlsx”，先单独处理名单，不要直接进入
提交匹配。

以下情况都必须先做名单标准化：

- 名单是图片、扫描 PDF、拍照 Word、截图型 PPT
- 名单虽然是 xlsx，但没有明确的 `学号` / `姓名` 表头
- 名单里没有学号，只给了姓名、座位、分组等信息
- 名单混有大量说明文字、页眉页脚、班级说明，无法直接回写

先启动一个专门的 roster-normalizer 子 agent。它只负责识别名单，不负责批改作业。
详细规则见 `references/roster-normalization.md` 与
`references/normalized-roster-schema.md`。

roster-normalizer 的产物必须有两份：

- `roster.normalized.json`：结构化名单
- `roster.normalized.xlsx`：标准化回写底表

从 JSON 生成标准化 xlsx：

```bash
python3 scripts/build_roster_xlsx.py \
  --roster-json "<run_dir>/roster.normalized.json" \
  --output "<run_dir>/roster.normalized.xlsx"
```

如果名单缺少学号，不要阻塞流程；允许生成“姓名优先”的标准化名单，但后续匹配与
回写要开启 `--allow-missing-ids`。

完整模板见 `references/agent-prompts.md` 中的
“roster-normalizer 子 agent 模板”。

### 1. 建立题目基线

先完整读取题目材料，输出一份面向所有子 agent 共享的“评分基线”：

- 题目目标与交付物
- 每题或每部分的评分点
- 总分与扣分原则
- 允许的合理变体
- 明确的人工复核条件

若题目本身也是图片化材料，按
`references/file-type-playbook.md` 的“图片优先文档”流程处理。

### 2. 生成提交清单

先运行脚本生成名单和提交物的匹配清单：

```bash
python3 scripts/match_submissions.py \
  --roster "<normalized_roster_xlsx>" \
  --submissions-dir "<submissions_dir>" \
  --output "<run_dir>/manifest.json"
```

如果标准化名单里存在空学号行，再额外加上：

```bash
  --allow-missing-ids
```

脚本会输出：

- 已匹配学生及其提交路径
- 未匹配学生
- 无法归属的文件
- 多学生歧义文件

对未匹配或歧义项，不要直接打分；先标记为 `missing` 或 `ambiguous`。

### 3. 分批调度子 agent

只让主 agent 负责调度和汇总；每个子 agent 只负责一个学生作业。

- 每批启动 `3-4` 个 `worker` 子 agent
- 每个子 agent 只拥有一个学生的提交路径
- 主 agent 在子 agent 运行时继续准备下一批，不空转
- 任一子 agent 完成后，立即补上下一个学生，保持并发稳定

对子 agent 的要求：

- 只写自己的结果文件 `reviews/<student_id>.json`
- 不改学生原始作业
- 不越权处理其他学生
- 遇到读不出的材料时，先尝试格式分流；仍无法判断时输出
  `needs_manual_review=true`

完整模板见 `references/agent-prompts.md` 中的
“单学生批改 worker 模板”。

### 4. 单份作业审阅

对每个学生都执行同一套规则：

1. 先识别提交物类型
2. 优先读取原生文本
3. 对图片化内容切换到 `view_image`
4. 只基于实际看到的内容评分
5. 输出结构化结果 JSON

常见格式分流详见 `references/file-type-playbook.md`。

### 5. 汇总与回写名单

当一批结果完成后，主 agent 先抽查明显异常项，再把已确认结果回写名单：

```bash
python3 scripts/update_roster_xlsx.py \
  --roster "<normalized_roster_xlsx>" \
  --review-source "<run_dir>/reviews" \
  --score-column "<score_column>" \
  --comment-column "<comment_column>" \
  --status-column "<status_column>" \
  --output "<run_dir>/students-reviewed.xlsx"
```

如果标准化名单里存在空学号行，再额外加上：

```bash
  --allow-missing-ids
```

脚本默认生成新文件，不直接覆盖原名单。确认无误后，再决定是否替换原文件。

## 文件处理边界

- 优先支持：`txt md csv json py c cpp java js ts html css ipynb pdf docx pptx jpg jpeg png webp bmp zip`
- `pdf/docx/pptx` 不保证一定有可提取正文；文本为空时必须转图片路径
- `zip` 先解压到临时目录，再递归分析内部有效文件
- 学生名单也按同样的分流规则处理；只是名单识别必须先于作业批改
- `rar/7z`、视频、音频、损坏文档默认标记为 `unsupported` 或
  `manual_review`

## 结果标准

始终让结果可回写、可追溯、可复核：

- `score` 只写数值
- `comment` 保持一行短评，适合回填名单
- `summary` 用于主 agent 汇总
- `evidence` 必须指向实际页、图、文件或片段
- `deductions` 记录每次扣分及原因

在写入名单之前，先读取 `references/review-result-schema.md`，确保各子
agent 产出的字段一致。
