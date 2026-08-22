# 使用文档

`main.py` 是统一的入口,内部仍然是两段式管线:

```
PDF ──► 阶段一: PaddleOCR 版面识别 (paddle_convert.py) ──► Markdown + imgs/ ──► 阶段二: EPUB 打包 (build_epub.py) ──► EPUB
```

两个阶段互相解耦:`--skip-epub` 只做 OCR,`--skip-md` 只用已有的 Markdown 重建 EPUB。
每个阶段也都可以单独调用底层脚本(`python paddle_convert.py ...` / `python build_epub.py ...`)。

## 快速开始

```bash
# 单本
python main.py 某书.pdf

# 整个目录（默认：把 PDF 丢进 ./input/ 后直接 python main.py）
python main.py ./books/

# 只 OCR 到 Markdown，不生成 EPUB
python main.py 某书.pdf --skip-epub

# 手工校对过 Markdown 后，只重新打包 EPUB
python main.py 某书.pdf --skip-md --title "书名" --author "作者"

# 先转几页试水，确认效果再跑全书
python main.py 某书.pdf --start-page 0 --max-pages 20
```

## 完整参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `input` | `./input/` | PDF 文件或目录 |
| `output` | 紧邻 PDF 的 `<书名>/` | Markdown / 图片输出目录 |
| `--skip-epub` | — | 只做 PDF → Markdown |
| `--skip-md` | — | 只做 Markdown → EPUB |
| `--start-page` | `0` | 起始页(0 起) |
| `--max-pages` | 全书 | 最多转换页数 |
| `--dpi` | `200` | 渲染分辨率;越低越快,字小再调回 200 |
| `--lang` | `ch` | PaddleOCR 识别语言(见下) |
| `--title / --author / --publisher / --isbn` | 自动推断 | EPUB 元数据 |
| `--epub-language` | `zh` | EPUB `<dc:language>` |

不传 `--title` 等元数据参数时,书名从 Markdown 首个 `# ` 标题推断,其余留空。

## 语言支持(重要)

本项目**针对简体中文扫描书(非虚构 / 散文类)调优**:

- 版面模型默认 `lang="ch"`,识别中文排版(竖排、段落、脚注)最稳;
- `paddle_convert.py` 里的后处理启发式规则(`fix_latex` / `fix_paragraph_breaks` /
  `remove_noise_heads`)是针对**中文散文**的 OCR 瑕疵设计的——例如段落被版面模型拆开后的空行合并、
  脚注上标 `\textcircled{1}` → `①`、红色化名 `××` 的 LaTeX 噪声还原。
- 换用其他语言时,PaddleOCR 仍能识别(`--lang` 传对应代码,如 `en`),但**不享受上述中文后处理修复**,
  输出可能残留更多 OCR 噪声,需要自行人工校对。

如果你主要转换的是英文或其他语言的书,请在 README 里说明这是中文优化的工具,或者另开分支去掉中文专用规则。

## 性能与硬件

| 环境 | 370 页 / 200 DPI 参考 | 单页 |
|---|---|---|
| RTX 4060 8GB | ≈ 12 分钟 | ≈ 2 秒 |
| 现代 CPU(8–16 核,server 模型) | ≈ 3–5 小时 | 30–50 秒 |
| 现代 CPU(mobile 模型,关去卷曲) | ≈ 40–90 分钟 | 7–15 秒 |

CPU 慢的根本原因是用了 **server 级模型**(`PP-OCRv5_server_det/rec`),参数量大、逐行识别串行、
还要叠 UVDoc 去卷曲和方向分类的推理 pass。GPU 有 tensor core,有效算力高一个数量级以上。

**CPU 提速建议**:在 `paddle_convert.py` 的 `build_pipeline()` 里把检测/识别模型换成
`PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec`(通常快 5–10 倍,散文书精度够用),并关闭
`use_doc_unwarping` / `use_doc_orientation_classify`;命令行配合 `--dpi 150` 进一步加速。
首次运行前先用 `--max-pages 5` 量一下单页耗时再决定全书。

## 结果检查

转换完成后**建议抽查开头 / 目录 / 各分部标题**,人工修掉极少数整页错乱——OCR 对极花哨的排版页
仍会偶尔失手。这正是两段式管线存在的意义:Markdown 可随意改,改完 `--skip-md` 重新打包即可。
