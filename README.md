# scanpdf_2_epub

把**扫描版 PDF 图书**转换成可读的 **Markdown** 与中文排版 **EPUB**。

针对中文简体扫描书（非虚构 / 散文类）调优：约 **370 页 12 分钟**完成（RTX 4060 8GB，200 DPI）。

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

## 安装

建议 Python 3.10+。GPU 版依赖安装（清华 pip 镜像 + Paddle cu126 官方源）：

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

> 无 GPU 时：第一步改为 `pip install paddlepaddle`，OCR 速度明显变慢但不影响正确性。

首次运行会下载 PP-DocLayout_plus-L、PP-OCRv5_server_det/rec、UVDoc 等模型到 `~/.paddlex/`，
国内网络可将 `PADDLE_PDX_MODEL_SOURCE` 指向镜像。

## 使用

### 1. PDF → Markdown

```bash
python paddle_convert.py 某书.pdf                      # 全书
python paddle_convert.py 某书.pdf --start-page 20 --max-pages 20   # 只转 20 页试水
python paddle_convert.py 某书.pdf --dpi 150            # 低 DPI 更快，字小的话再调回 200
```

输出：`某书/某书.md` + `某书/imgs/*.jpg`。完成后建议**抽查开头 / 目录 / 各分部标题**，
人工修掉极少数整页错乱（OCR 对极花哨排版页仍会偶尔失手）。

### 2. Markdown → EPUB

```bash
python build_epub.py 某书.pdf --md 某书/某书.md --output 某书.epub \
    --title "书名" --author "作者" --publisher "出版社" --isbn "978-7-xxxx-xxxx-x"
```

不传 `--title` 等参数时，会自动从 Markdown 首个 `# ` 标题推断书名，其余留空。

## 项目结构

```
scanpdf_2_epub/
├── paddle_convert.py    # 阶段一：PDF → Markdown（版面解析 + 后处理）
├── build_epub.py        # 阶段二：Markdown → EPUB（中文排版、封面、目录）
├── requirements.txt
└── README.md
```

## 已知限制

- 章节标题依赖 Markdown 里的 `#` / `##` 层级：封面页与目录之前的内容会被跳过，`###` 小节并入上一章。
- 公式识别仅做噪声清理（`××` 还原），本项目定位是**散文 / 非虚构**扫描书；
  带大量真公式的科技书请换 marker-pdf 类方案。
- 转换产物（`.md` / `.epub` / `imgs/`）体积大且可能是版权内容，默认已加入 `.gitignore`。

## License

[MIT](LICENSE)
