# 提示模板

下面给出可直接复制的提示模板。把尖括号占位符替换成真实值即可。

## 1. 全量批改主 agent 模板

```text
使用 $batch-homework-review 完成一次整批作业自动审阅。

输入参数：
- submissions_dir: <学生作业目录>
- assignment_path: <题目文件或题目目录>
- roster_path: <原始学生名单路径>
- run_dir: <输出运行目录，例如 /path/_review_runs/20260427-153000>
- batch_size: <3 或 4>
- max_score: <总分，默认 100>
- score_column: <总分 或其他列名/列字母>
- comment_column: <评语 或其他列名/列字母>
- status_column: <状态 或其他列名/列字母>

执行要求：
1. 先创建 run_dir，并确保至少包含：
   - <run_dir>/reviews
   - <run_dir>/extracted
2. 先判断 roster_path 是否已经是可直接回写的标准 xlsx。
3. 如果不是标准 xlsx，或缺少明确表头，先启动一个 worker 子 agent 作为 roster-normalizer：
   - 它只负责识别名单
   - 它的输出必须写到 <run_dir>/roster.normalized.json
4. 名单标准化完成后，运行：
   - python3 scripts/build_roster_xlsx.py --roster-json "<run_dir>/roster.normalized.json" --output "<run_dir>/roster.normalized.xlsx"
5. 如果名单已经是标准 xlsx，也要先确认是否存在“学号/姓名”表头、是否可稳定回写；若不能，仍转为 normalized 版本。
6. 读取 assignment_path，建立统一评分基线，写出你自己的内部摘要，至少包含：
   - 题目目标
   - 每题评分点
   - 总分与扣分原则
   - 允许的合理变体
   - 需要人工复核的条件
7. 运行匹配脚本生成 manifest：
   - 名单学号完整时：
     python3 scripts/match_submissions.py --roster "<run_dir>/roster.normalized.xlsx" --submissions-dir "<submissions_dir>" --output "<run_dir>/manifest.json"
   - 名单存在空学号行时：
     python3 scripts/match_submissions.py --roster "<run_dir>/roster.normalized.xlsx" --submissions-dir "<submissions_dir>" --allow-missing-ids --output "<run_dir>/manifest.json"
8. 从 manifest 中提取已匹配学生，按 batch_size 启动 worker 子 agent 并行批改；每个 worker 只负责一个学生，不要把多个学生交给同一个 worker。
9. 主 agent 不要空等；任一 worker 完成后，立即补上下一个未处理学生，保持并发稳定。
10. 每个 worker 必须把结果写到 <run_dir>/reviews/<student_key>.json。
11. 每一批完成后，先抽查异常项：
   - 缺作业
   - 同名歧义
   - 图片过糊
   - 只看到部分页面
   - 压缩包损坏
12. 抽查后回写名单：
   - 正常名单：
     python3 scripts/update_roster_xlsx.py --roster "<run_dir>/roster.normalized.xlsx" --review-source "<run_dir>/reviews" --score-column "<score_column>" --comment-column "<comment_column>" --status-column "<status_column>" --output "<run_dir>/students-reviewed.xlsx"
   - 存在空学号行：
     python3 scripts/update_roster_xlsx.py --roster "<run_dir>/roster.normalized.xlsx" --review-source "<run_dir>/reviews" --score-column "<score_column>" --comment-column "<comment_column>" --status-column "<status_column>" --allow-missing-ids --output "<run_dir>/students-reviewed.xlsx"
13. 最终输出时给出：
   - 标准化名单路径
   - manifest 路径
   - 回写后的名单路径
   - 已审阅人数 / 未匹配人数 / 需人工复核人数
   - 主要风险与后续建议

约束：
1. 不要修改学生原始作业。
2. 不要把未确认归属的作业直接算到某个学生名下。
3. 图片化内容必须使用 view_image 实际查看。
4. pdf/docx/pptx 先尝试原生文本，失败后再走图片分流。
5. zip 先解压到 <run_dir>/extracted，再递归分析有效文件。
```

## 2. 仅名单标准化主 agent 模板

```text
使用 $batch-homework-review 只完成学生名单标准化，不做作业批改。

输入参数：
- roster_path: <原始名单路径>
- run_dir: <输出运行目录>

执行要求：
1. 启动一个 worker 子 agent 作为 roster-normalizer。
2. 它必须读取原始名单的真实内容，而不是只依据文件名。
3. 它的输出写到 <run_dir>/roster.normalized.json，并符合 references/normalized-roster-schema.md。
4. 然后运行：
   python3 scripts/build_roster_xlsx.py --roster-json "<run_dir>/roster.normalized.json" --output "<run_dir>/roster.normalized.xlsx"
5. 最终输出：
   - 标准化 JSON 路径
   - 标准化 xlsx 路径
   - 名单总人数
   - 缺学号人数
   - 需人工复核人数
   - 主要识别风险
```

## 3. roster-normalizer 子 agent 模板

```text
使用 $batch-homework-review 只处理学生名单标准化。

你只负责一个名单文件：
- roster_path: <原始名单路径>
- output_json: <run_dir>/roster.normalized.json

工作目标：
把原始名单转换为结构化 JSON，供后续生成标准化 xlsx 和回写使用。

工作步骤：
1. 先识别 roster_path 的文件类型。
2. 按 references/file-type-playbook.md 读取内容：
   - 文本足够时直接读文本
   - 图片化内容用 view_image
   - docx/pptx/pdf 若正文不可靠，转图片再看
3. 逐页、逐块、逐行抽取学生记录。
4. 输出必须符合 references/normalized-roster-schema.md。

字段要求：
1. 能识别学号就写 student_id；不能确认时留空，不要瞎补。
2. 尽量提取 student_name；如果这是唯一可靠标识，必须保留。
3. 尽量补充：
   - gender
   - class_name
   - group_name
   - seat_number
4. 每条记录都要给 source_evidence。
5. 每条记录都要给 confidence。

识别要求：
1. 不要把课程名、页码、教师名、注释行当成学生。
2. 即使页面上没有明确写“学号”“姓名”，也要依据版式判断学生记录。
3. 同名学生不要合并。
4. 对看不清、被遮挡、页间断裂的记录，设置 needs_manual_review=true。
5. 如果整份名单学号普遍缺失，设置 matching_mode_hint=name_first。
6. 如果学号普遍完整，设置 matching_mode_hint=id_first。

输出要求：
1. 只写 output_json，不要改别的文件。
2. 输出前自检：
   - students 数组是否存在
   - 每条记录是否至少有 student_id 或 student_name
   - 是否存在明显说明文字误入 students
```

## 4. 单学生批改 worker 模板

```text
使用 $batch-homework-review 审阅单个学生作业。

你只负责这一个学生：
- student_id: <student_id，可为空>
- student_name: <student_name>
- submission_paths: <该学生提交物路径列表>
- assignment_baseline: <主 agent 提供的评分基线>
- output_json: <run_dir>/reviews/<student_key>.json

工作步骤：
1. 先检查 submission_paths 是否为空；为空则输出 missing 结果。
2. 对每个提交物先识别文件类型，再按 references/file-type-playbook.md 读取。
3. 读取优先级：
   - 能直接读文本就先读文本
   - 文本不足时转图片
   - 图片、扫描件、手写页直接走 view_image
   - zip 先解压再递归分析内部有效文件
4. 对照 assignment_baseline 逐项评分。
5. 把结果写入 output_json，格式必须符合 references/review-result-schema.md。

评分要求：
1. 只基于你实际看到的内容评分。
2. evidence 必须落到具体页、图、文件、题号或代码片段。
3. deductions 必须说明扣了多少分、为什么扣。
4. comment 保持一行短评，适合回填名单。
5. summary 给主 agent 汇总用，可以略完整一些。

异常处理：
1. 文件损坏、格式不支持、只看到一部分、图片过糊时，不要硬判。
2. 无法可靠判分时，设置：
   - status=manual_review 或 unsupported
   - needs_manual_review=true
3. 若提交物疑似不属于该学生，也要写入异常说明。

输出约束：
1. 只写这个学生自己的 output_json。
2. 不要修改学生原始作业。
3. 不要处理其他学生。
```

## 5. 批量回写前复核模板

```text
使用 $batch-homework-review 做结果汇总与回写前复核。

输入参数：
- normalized_roster_xlsx: <标准化名单 xlsx>
- review_dir: <reviews 目录>
- manifest_path: <manifest.json>
- score_column: <总分 或其他列>
- comment_column: <评语 或其他列>
- status_column: <状态 或其他列>
- allow_missing_ids: <true 或 false>

执行要求：
1. 先检查是否存在这些异常：
   - manifest 中 unmatched_students 非空
   - manifest 中 ambiguous_files 非空
   - review_dir 中缺少某些已匹配学生的结果文件
   - review 结果里 needs_manual_review=true
   - 同名且无学号学生可能冲突
2. 汇总异常人数和名单。
3. 仅在结果足够完整时执行回写脚本。
4. 回写后输出：
   - 回写文件路径
   - updated_rows
   - unresolved 列表
   - 建议人工复核的学生
```

## 6. 断点续跑主 agent 模板

```text
使用 $batch-homework-review 从已有 run_dir 继续批改，不重新开始。

输入参数：
- run_dir: <已有运行目录>
- submissions_dir: <学生作业目录>
- assignment_path: <题目文件或题目目录>
- normalized_roster_xlsx: <已存在的 roster.normalized.xlsx>
- batch_size: <3 或 4>

执行要求：
1. 读取 <run_dir>/manifest.json 与 <run_dir>/reviews/*.json。
2. 找出：
   - 已完成学生
   - 未完成学生
   - 需要人工复核学生
3. 只对未完成学生继续启动 worker。
4. 不要覆盖已经存在且结构正确的 review JSON，除非明确发现损坏或空文件。
5. 全部补齐后，再执行一次回写。
```
