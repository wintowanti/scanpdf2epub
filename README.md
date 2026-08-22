# scanpdf2epub

把**扫描版 PDF 图书**转换成可读的 **Markdown** 与中文排版 **EPUB**。

针对**简体中文扫描书（非虚构 / 散文类）调优**：约 **370 页 12 分钟**完成（RTX 4060 8GB，200 DPI）。

```
PDF ──► paddle_convert.py ──► 同名/同名.md + imgs/ ──► build_epub.py ──► 同名.epub
      (PaddleOCR 版面识别)                      (ebooklib 打包 EPUB3)
```

---

## 为什么用 PaddleOCR

早期用 marker-pdf 方案实测：370 页耗时约 **11 小时且中途崩溃**。PaddleX `PPStructureV3` 管线
把整本书切成 16 页一块 / 每批 4 页处理，内存有界、速度约快 50 倍，中文识别质量也明显更好。

## 特性

- **两段式管线**：先 PDF→Markdown（可人工校对、修错），再 Markdown→EPUB，互不耦合。
- **统一入口 `main.py`**：单本或整个目录批量处理；`--skip-epub` / `--skip-md` 可单独跑任一段。
- **版面解析**（PPStructureV3）：文档方向 / 文字方向 / UVDoc 去卷曲 / 表格 / 公式 / 图片，块内容输出 Markdown。
- **中文散文后处理**：自动修复 OCR 常见瑕疵——
  - 版面模型把一个自然段拆成多块导致的**多余空行**（按「段末句子标点 + 下一行首字符」启发式合并）；
  - 公式误识别把文中的红色化名 `××` 识别成 LaTeX 噪声 → 还原；
  - 脚注上标 `\textcircled{1}` → `①`、`\mathrm{VP}` → `VP`；
  - 纯装饰分隔页噪声标题（`## ***`）删除。
- **图片按坐标裁剪**：嵌套图片块的 `img_in_image_box_<x1>_<y1>_<x2>_<y2>.jpg` 文件名直接携带块 bbox，从整页像素里裁剪保存。
- **中文排版 EPUB**：正文首行缩进 2em、行高 1.85、两端对齐、衬线 CJK 字体栈；PDF 首页渲染为封面；
  目录/页脚由 ebooklib 原生生成（不依赖 Markdown 自带的「目录」章节）。
- **元数据自动推断**：从 Markdown 首个 `# ` 标题猜书名，也可用命令行参数覆盖。

## 语言支持（重要）

本项目**面向简体中文扫描书**。版面模型默认 `lang="ch"`，`paddle_convert.py` 里的后处理启发式
（段落空行合并、`×`×` 还原、脚注上标、噪声标题清理）也都是为**中文散文**的 OCR 瑕疵设计的。

- 换用其他语言时，PaddleOCR 仍能识别（`--lang en` 等），但**不享受中文专用修复**，输出可能残留更多噪声。
- 如需处理英文书，请在 issue 里说明，或另起分支剥离中文专用规则。

## 安装

建议 Python 3.10–3.12（PaddlePaddle 3.3.x 支持）。GPU 版依赖安装（清华 pip 镜像 + Paddle cu126 官方源）：

```bash
python -m venv .venv-paddle
source .venv-paddle/bin/activate

# 1) PaddlePaddle GPU（RTX 系列 cu126；CPU 可换成 paddlepaddle）
pip install -U pip
pip install paddlepaddle-gpu==3.3.1 \
    -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

# 2) 其余依赖（清华镜像）
pip install -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> 无 GPU 时：第一步改为 `pip install paddlepaddle`，OCR 速度明显变慢但不影响正确性（耗时对比见「性能与硬件」）。

首次运行会下载 PP-DocLayout_plus-L、PP-OCRv5_server_det/rec、UVDoc 等模型到 `~/.paddlex/`，
国内网络可将 `PADDLE_PDX_MODEL_SOURCE` 指向镜像。

## 使用

详细文档见 [docs/USAGE.md](docs/USAGE.md)。推荐用统一入口 `main.py`：

```bash
# 单本：PDF → Markdown → EPUB
python main.py 某书.pdf

# 整个目录批量（默认 ./input/，把 PDF 丢进去即可）
python main.py ./books/

# 只 OCR 到 Markdown，不生成 EPUB（方便先校对）
python main.py 某书.pdf --skip-epub

# 校对完 Markdown 后，只重新打包 EPUB
python main.py 某书.pdf --skip-md --title "书名" --author "作者"

# 先转 20 页试水；CPU 上可加 --dpi 150 提速
python main.py 某书.pdf --start-page 0 --max-pages 20
```

也可以单独调用两个阶段的脚本：

```bash
python paddle_convert.py 某书.pdf                     # 阶段一：PDF → Markdown
python paddle_convert.py 某书.pdf --dpi 150            # 低 DPI 更快，字小的话再调回 200
python build_epub.py 某书.pdf --md 某书/某书.md --output 某书.epub \
    --title "书名" --author "作者" --publisher "出版社" --isbn "978-7-xxxx-xxxx-x"
```

输出：`某书/某书.md` + `某书/imgs/*.jpg`，EPUB 生成在 PDF 旁。完成后建议**抽查开头 / 目录 / 各分部标题**，
人工修掉极少数整页错乱（OCR 对极花哨排版页仍会偶尔失手）。

## Demo：合成扫描 PDF

没有扫描书也能先测管线。`demo/make_demo_pdf.py` 用原创中文散文生成**带扫描噪声的图片页 PDF**，
行为和复印书页一致，可放心提交、无版权问题：

```bash
python demo/make_demo_pdf.py --pages 6        # 生成 demo/output/demo_6p.pdf
python main.py demo/demo_4p.pdf --max-pages 1 # 仓库自带 4 页样例，克隆即可试
```

## 性能与硬件

| 环境 | 370 页 / 200 DPI 参考 | 单页 |
|---|---|---|
| RTX 4060 8GB | ≈ 12 分钟 | ≈ 2 秒 |
| 现代 CPU（8–16 核，server 模型） | ≈ 3–5 小时 | 30–50 秒 |
| 现代 CPU（mobile 模型 + 关去卷曲） | ≈ 40–90 分钟 | 7–15 秒 |

CPU 慢的根源是用 **server 级模型**（`PP-OCRv5_server_det/rec`）：参数量大、逐行识别串行，还要叠
UVDoc 去卷曲和方向分类的推理 pass；GPU 有 tensor core，有效算力高一个数量级以上。
**CPU 提速**：把 `build_pipeline()` 换成 `PP-OCRv5_mobile_det/rec`（散文书精度够用），并关闭
`use_doc_unwarping` / `use_doc_orientation_classify`；配合 `--dpi 150`。详见 [docs/USAGE.md](docs/USAGE.md)。

## 项目结构

```
scanpdf2epub/
├── main.py               # 统一入口：批量 / 两段管线 / 阶段开关
├── paddle_convert.py     # 阶段一：PDF → Markdown（版面解析 + 后处理）
├── build_epub.py         # 阶段二：Markdown → EPUB（中文排版、封面、目录）
├── demo/
│   ├── make_demo_pdf.py  # 合成扫描 PDF 生成器
│   ├── demo_4p.pdf       # 4 页小样例（克隆即可试）
│   └── README.md
├── docs/USAGE.md         # 完整使用 / 语种 / 性能文档
├── .github/workflows/ci.yml   # CI：语法检查 + ruff（E9/F）
├── requirements.txt
└── README.md
```

## 已知限制

- 章节标题依赖 Markdown 里的 `#` / `##` 层级：封面页与目录之前的内容会被跳过，`###` 小节并入上一章。
- 公式识别仅做噪声清理（`××` 还原），本项目定位是**散文 / 非虚构**扫描书；
  带大量真公式的科技书请换 marker-pdf 类方案。
- 后处理规则为**中文散文**调优，非中文书籍不享受这些修复。
- 转换产物（`.md` / `.epub` / `imgs/`）体积大且可能是版权内容，默认已加入 `.gitignore`。

## License

[MIT](LICENSE)
