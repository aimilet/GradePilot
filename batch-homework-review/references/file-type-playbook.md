# 文件类型处理手册

按“先原生文本，后图片查看”的顺序处理提交物。不要只根据扩展名打分。

## 1. 纯文本与代码

适用：

- `txt`
- `md`
- `csv`
- `json`
- `py`, `c`, `cpp`, `java`, `js`, `ts`
- `html`, `css`

做法：

- 先读 `README`、主程序入口、题目相关文件
- 用 `rg` 找关键字、函数名、题号
- 只在需要时运行只读检查；默认不要执行会改文件的命令

## 2. PDF

先判断是否能直接取到正文：

```bash
pdfinfo "<file.pdf>"
pdftotext -layout "<file.pdf>" -
```

如果正文充分可读，直接审阅文本。

如果正文为空、乱码明显、或页面主要是截图/手写/扫描：

```bash
mutool draw -F png -o "/tmp/review-page-%d.png" "<file.pdf>"
```

然后对关键页逐张调用 `view_image`。

## 3. DOCX

先解压并检查正文 XML：

```bash
unzip -l "<file.docx>"
```

重点看：

- `word/document.xml`
- `word/media/*`

如果 `document.xml` 里有正常文本，优先读文本。

如果正文几乎只有图片、文本框为空、或内容本来就是拍照页：

- 提取 `word/media/*`
- 对关键图片调用 `view_image`

## 4. PPTX

先解压并检查每页文本：

```bash
unzip -l "<file.pptx>"
```

重点看：

- `ppt/slides/slide*.xml`
- `ppt/media/*`

如果幻灯片文本充分，直接按页审阅。

如果主要是整页截图、拍照课件、手写图：

- 提取 `ppt/media/*`
- 对关键图片调用 `view_image`

## 5. 图片

适用：

- `jpg`, `jpeg`, `png`, `webp`, `bmp`

做法：

- 直接调用 `view_image`
- 只依据实际看见的内容给结论
- 若局部看不清，记录“不确定”并触发人工复核

## 6. ZIP

先解压到临时目录，再递归处理内部文件：

```bash
unzip -o "<file.zip>" -d "<temp_dir>"
```

处理规则：

- 忽略 `__MACOSX/`、`.DS_Store`、缩略图等垃圾文件
- 若内部已存在按学生分目录的结构，把目录视作该学生的提交根
- 若内部还有 `pdf/docx/pptx/图片`，继续按本手册分流

## 7. 不支持或高风险格式

默认不要自行处理：

- `rar`
- `7z`
- 视频
- 音频
- 加密文档
- 已损坏文档

对这些情况：

- 输出 `status=unsupported` 或 `status=manual_review`
- 在结果里写清楚阻塞原因

## 8. 证据写法

证据必须指向实际载体，例如：

- `第 2 页 PDF 显示……`
- `docx 的第 3 张嵌入图片包含……`
- `slide 4 文本框给出了……`
- `main.py 中函数 solve 未处理边界条件`

不要写“看起来像”“估计是”。无法确定就标记人工复核。

## 9. 名单文件的额外要求

当读取的是学生名单，而不是学生作业时：

- 目标从“评分”切换为“抽取学生记录”
- 要按连续行、重复列、页面布局识别学生清单
- 即使没有出现明确的 `学号` / `姓名` 字样，也要结合版式判断字段
- 名单标准化结果必须写入 `references/normalized-roster-schema.md`
