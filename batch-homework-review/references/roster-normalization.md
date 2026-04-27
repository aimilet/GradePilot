# 名单标准化流程

先把原始名单转换为统一的结构化名单，再进入作业匹配与回写。

## 目标

无论原始名单来自：

- `.xlsx`
- `.pdf`
- `.docx`
- `.pptx`
- `.jpg/.png`

都要最终落成两份产物：

- `roster.normalized.json`
- `roster.normalized.xlsx`

## roster-normalizer 子 agent 职责

它只做名单识别，不做作业评分。

输出时重点保证：

- 尽量抽出 `student_name`
- 能抽出学号就写 `student_id`
- 不能抽出学号时允许为空
- 用 `source_evidence` 标明来自哪一页、哪一段、哪一张图
- 用 `confidence` 标明把握程度

## 名单识别顺序

### 1. 判断是不是标准 xlsx

如果是 xlsx，先检查：

- 是否存在清晰表头
- 是否可稳定识别出“每行一个学生”
- 是否能定位后续回写列

若满足这些条件，可直接把它视为“已标准化名单”，或先转成
`roster.normalized.json` 再生成标准化 xlsx。

### 2. 对图片化名单逐页读取

对图片、扫描 PDF、拍照 Word、截图型 PPT：

- 优先抽出每一页的学生记录
- 必要时逐张图片调用 `view_image`
- 不要依赖原文里必须出现“学号”“姓名”字样

很多名单只会表现为：

- 第一列是序号
- 第二列是学号或姓名
- 后面是专业、分组、座位、到课状态

要根据整页版式、列重复模式、行间距来判断字段含义。

### 3. 处理字段缺失

如果名单里没有学号：

- `student_id` 留空
- 继续保留 `student_name`
- 尽可能补 `seat_number`、`group_name`、`class_name`
- 设置 `matching_mode_hint=name_first`

如果只有学号没有姓名：

- 仍可保留记录
- 但后续匹配学生提交物会很弱，标记 `needs_manual_review=true`

### 4. 处理页眉页脚和说明文字

不要把这些当成学生记录：

- 课程名
- 学院名
- 教师名
- 页码
- 说明段落
- “带*号学生……”之类注释

一条学生记录通常应至少满足以下之一：

- 有姓名
- 有学号
- 在版式上处于连续学生行区域中

## 生成标准化 xlsx

名单 JSON 生成后，运行：

```bash
python3 scripts/build_roster_xlsx.py \
  --roster-json "<run_dir>/roster.normalized.json" \
  --output "<run_dir>/roster.normalized.xlsx"
```

生成后的 xlsx 默认表头包含：

- `序号`
- `学号`
- `姓名`
- `性别`
- `专业/班级`
- `分组`
- `座位`
- `来源证据`
- `置信度`
- `备注`
- `总分`
- `评语`
- `状态`

后续匹配与回写都针对这份标准化 xlsx 进行。
