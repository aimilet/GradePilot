# 作业自动审阅 Skill

本仓库提供一个可供 Codex 显式调用的本地 skill：
[batch-homework-review](./batch-homework-review/SKILL.md)。

它的目标是把“学生名单识别 -> 作业匹配 -> 多子 agent 并行审阅 -> 成绩回写”
串成一条可重复执行的工作流，适合批量批改课程作业。

## 功能概览

- 支持先识别原始学生名单，再生成标准化回写底表
- 支持按学号或姓名匹配学生提交物
- 支持 `3-4` 个子 agent 并行批改
- 支持 `pdf/docx/pptx/图片/zip` 等常见提交格式
- 支持把评分结果写回标准化 `.xlsx` 名单
- 支持断点续跑与人工复核标记

## 目录结构

```text
.
├── batch-homework-review/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/
│   │   ├── agent-prompts.md
│   │   ├── file-type-playbook.md
│   │   ├── normalized-roster-schema.md
│   │   ├── review-result-schema.md
│   │   └── roster-normalization.md
│   └── scripts/
│       ├── build_roster_xlsx.py
│       ├── match_submissions.py
│       ├── update_roster_xlsx.py
│       └── xlsx_roster.py
```

## 适用场景

当你需要让 Codex 批量审阅学生作业，并且具备下面任一条件时，可以显式调用
`$batch-homework-review`：

- 学生名单不是标准 Excel，而是图片、PDF、Word、PPT
- 学生提交格式不统一，既有文档也有图片或压缩包
- 希望把每个学生交给独立子 agent 审阅
- 希望最后把分数、评语、状态回写到统一名单

## 支持的输入

### 1. 学生名单

支持：

- `.xlsx`
- `.pdf`
- `.docx`
- `.pptx`
- `.jpg/.jpeg/.png`

名单不要求一定出现“学号”“姓名”表头。skill 会先走一层**名单标准化**：

1. 启动 `roster-normalizer` 子 agent 识别原始名单
2. 生成 `roster.normalized.json`
3. 再生成 `roster.normalized.xlsx`

后续所有匹配与回写都围绕标准化后的 `.xlsx` 进行。

### 2. 学生作业

支持：

- 纯文本和代码：`txt/md/csv/json/py/c/cpp/java/js/ts/html/css`
- 文档：`pdf/docx/pptx`
- 图片：`jpg/jpeg/png/webp/bmp`
- 压缩包：`zip`

其中：

- `pdf/docx/pptx` 会先尝试正文抽取
- 若正文不足或内容是扫描/截图/手写页，则转到 `view_image`
- `zip` 会先解压，再递归分析内部有效文件

## 核心流程

### 1. 名单标准化

原始名单先被转换成统一结构：

- `roster.normalized.json`
- `roster.normalized.xlsx`

对应脚本：

```bash
python3 batch-homework-review/scripts/build_roster_xlsx.py \
  --roster-json "<run_dir>/roster.normalized.json" \
  --output "<run_dir>/roster.normalized.xlsx"
```

### 2. 题目基线建立

主 agent 先读取题目材料，形成统一评分基线：

- 题目目标
- 每题评分点
- 总分
- 扣分原则
- 人工复核条件

### 3. 提交物匹配

把标准化名单与学生作业目录进行匹配：

```bash
python3 batch-homework-review/scripts/match_submissions.py \
  --roster "<run_dir>/roster.normalized.xlsx" \
  --submissions-dir "<submissions_dir>" \
  --output "<run_dir>/manifest.json"
```

如果名单里存在无学号学生：

```bash
python3 batch-homework-review/scripts/match_submissions.py \
  --roster "<run_dir>/roster.normalized.xlsx" \
  --submissions-dir "<submissions_dir>" \
  --allow-missing-ids \
  --output "<run_dir>/manifest.json"
```

### 4. 并行审阅

主 agent 按批次启动 `3-4` 个 worker 子 agent：

- 一个 worker 只负责一个学生
- 每个 worker 输出一个结构化 JSON
- 输出目录通常是 `<run_dir>/reviews/`

### 5. 成绩回写

审阅结果汇总后，写回标准化名单：

```bash
python3 batch-homework-review/scripts/update_roster_xlsx.py \
  --roster "<run_dir>/roster.normalized.xlsx" \
  --review-source "<run_dir>/reviews" \
  --score-column "总分" \
  --comment-column "评语" \
  --status-column "状态" \
  --output "<run_dir>/students-reviewed.xlsx"
```

如果名单里存在无学号学生：

```bash
python3 batch-homework-review/scripts/update_roster_xlsx.py \
  --roster "<run_dir>/roster.normalized.xlsx" \
  --review-source "<run_dir>/reviews" \
  --score-column "总分" \
  --comment-column "评语" \
  --status-column "状态" \
  --allow-missing-ids \
  --output "<run_dir>/students-reviewed.xlsx"
```

## 主要脚本说明

- [build_roster_xlsx.py](./batch-homework-review/scripts/build_roster_xlsx.py)
  把结构化名单 JSON 转成可回写的标准化 `.xlsx`
- [match_submissions.py](./batch-homework-review/scripts/match_submissions.py)
  按学号/姓名把名单和提交物匹配起来
- [update_roster_xlsx.py](./batch-homework-review/scripts/update_roster_xlsx.py)
  把评分结果回写到标准化名单
- [xlsx_roster.py](./batch-homework-review/scripts/xlsx_roster.py)
  提供 `.xlsx` 读取与回写的底层能力

## 提示模板

如果你想直接复制提示词给 Codex，用这里：

- [agent-prompts.md](./batch-homework-review/references/agent-prompts.md)

其中已经包含：

- 全量批改主 agent 模板
- 仅名单标准化模板
- `roster-normalizer` 子 agent 模板
- 单学生批改 worker 模板
- 回写前复核模板
- 断点续跑模板

## 运行产物示例

```text
_review_runs/20260427-153000/
├── roster.normalized.json
├── roster.normalized.xlsx
├── manifest.json
├── reviews/
│   ├── student-001.json
│   ├── student-002.json
│   └── ...
├── extracted/
└── students-reviewed.xlsx
```

## 结果文件约定

每个学生的审阅结果遵循：
[review-result-schema.md](./batch-homework-review/references/review-result-schema.md)

结果里至少应包含：

- `student_id`
- `student_name`
- `score`
- `comment`
- `summary`
- `deductions`
- `evidence`
- `needs_manual_review`

## 当前边界

- `zip` 已支持
- `rar/7z` 目前默认标记为 `unsupported` 或 `manual_review`
- 视频、音频、加密文档、损坏文档不做自动评分
- 名单中若同名且无学号，回写时会提示歧义，不会静默写错
- 图片化内容依赖 Codex 的 `view_image` 能力，不走本地 OCR 脚本

## 致谢
感谢**真诚、友善、团结、专业**的 Linuxdo 社区，让我学到那么多有关ai相关知识。
<p>
  <a href="https://linux.do">
    <img src="https://img.shields.io/badge/LinuxDo-community-1f6feb" alt="LinuxDo">
  </a>
</p>
- [LinuxDo](https://linux.do) 学 ai, 上 L 站!
