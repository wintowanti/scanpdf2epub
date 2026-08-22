#!/usr/bin/env python3
"""Generate synthetic *scanned* PDFs to test the pipeline end-to-end.

Pages are real printed Chinese text burned into grayscale images with scan
artifacts (slight skew, sensor noise, speckle) — so each page behaves exactly
like a photocopied book page and exercises the full OCR path, without needing
a copyrighted book. The prose is original sample text, safe to commit.

Usage:
  python demo/make_demo_pdf.py                  # -> demo/output/demo_6p.pdf
  python demo/make_demo_pdf.py --pages 12       # bigger sample
  python demo/make_demo_pdf.py --dpi 200 --seed 7
"""
import argparse
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

SECTIONS = ["开卷", "求知", "写作", "时间", "起步"]

# Original prose written for this demo (not from any published work).
PARAGRAPHS = [
    "读书是一种与作者的对话。我们翻开一页,便走进另一个人的思考;合上书页,却把那些念头带回了自己的生活。古人说开卷有益,其实有益的不仅是知识本身,还有反复咀嚼的耐心。读得多了,才会发现每一本书都是一扇窗,窗外各有风景。",
    "科学的进步从来不是一蹴而就的。一次测量可能带来一个问号,一条公式可能隐藏一片天地。真正的乐趣,在于沿着线索追问下去,让未知慢慢显出轮廓。提出问题往往比回答问题更难,因为它需要勇气承认自己还不明白。",
    "写作与阅读互为表里。好的写作者懂得取舍,知道哪些话值得说完,哪些话应当留给沉默。读者则在字里行间,捕捉那些没有写出来的意思。一篇好文章像一扇半开的门,留给人想象的空间,而不是把话说尽。",
    "时间是最公平的裁判。一天二十四小时,对每个人都不多不少;差别只在于我们怎样使用。专注的人把时间酿成成果,散漫的人把时间冲淡成水。善用时间的人并不总是忙碌,他们只是知道什么值得做,什么应当放下。",
    "面对困难,重要的是先迈出第一步。目标可以遥远,但脚下的路是一步一步走出来的。只要方向正确,走得慢一些也没有关系。许多看似无法逾越的障碍,走过去回头看,不过是路上的一道小坎。",
]


def _find_font():
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("No CJK font found. Install fonts-wqy-zenhei or fonts-noto-cjk.")


def _wrap(text, draw, font, max_width):
    """Wrap CJK text to fit `max_width`, respecting mid-string line breaks."""
    lines = []
    line = ""
    for ch in text:
        if draw.textlength(line + ch, font=font) <= max_width:
            line += ch
        else:
            lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines


def render_page(section, paragraphs, font_path, size=(1240, 1754), body_pt=30):
    """Render one book page as a PIL image, then add scan artifacts."""
    title_font = ImageFont.truetype(font_path, 40)
    body_font = ImageFont.truetype(font_path, body_pt)
    margin = 90
    line_h = int(body_pt * 1.95)
    indent = body_pt * 2  # first-line indent: 2 chars

    img = Image.new("RGB", size, (248, 248, 244))
    draw = ImageDraw.Draw(img)

    # Running header (page number + section), like a real book page
    draw.text((margin, 60), f"· {section} ·", font=ImageFont.truetype(font_path, 24), fill=(60, 60, 60))

    x = margin
    y = margin + 60
    draw.text((x, y), section, font=title_font, fill=(20, 20, 20))
    y += 110

    max_width = size[0] - 2 * margin
    for para in paragraphs:
        lines = _wrap(para, draw, body_font, max_width - indent)
        for i, ln in enumerate(lines):
            draw.text((x + (indent if i == 0 else 0), y), ln, font=body_font, fill=(25, 25, 25))
            y += line_h
        y += line_h  # paragraph gap

    # ---- scan artifacts: make it look like a photocopier scan ----
    arr = np.array(img).astype(np.float32)
    arr += np.random.normal(0, 2.5, arr.shape)          # sensor noise
    speckle = np.random.rand(*arr.shape[:2])[..., None] < 0.0008
    arr = np.where(speckle, np.random.randint(120, 200, arr.shape[:2] + (1,)), arr)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)

    # slight page skew (the pipeline has use_doc_unwarping / orientation repair)
    angle = random.uniform(-1.2, 1.2)
    img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=(248, 248, 244))
    return img


def main():
    ap = argparse.ArgumentParser(description="Generate a synthetic scanned PDF for testing.")
    ap.add_argument("--pages", type=int, default=6, help="number of pages (default: 6)")
    ap.add_argument("--dpi", type=int, default=150, help="PDF resolution hint (default: 150)")
    ap.add_argument("--seed", type=int, default=None, help="random seed for reproducible output")
    ap.add_argument("--out", default=None, help="output path (default: demo/output/demo_<N>p.pdf)")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    font = _find_font()

    imgs = []
    for i in range(args.pages):
        section = SECTIONS[i % len(SECTIONS)]
        start = (i * 2) % len(PARAGRAPHS)
        paras = PARAGRAPHS[start:start + 2] or PARAGRAPHS  # 2 paragraphs/page
        imgs.append(render_page(section, paras, font))

    out = Path(args.out) if args.out else Path(__file__).parent / "output" / f"demo_{args.pages}p.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(out, "PDF", save_all=True, append_images=imgs[1:], resolution=args.dpi)
    print(f"Demo scanned PDF: {out} ({args.pages} pages, {out.stat().st_size/1024:.0f} KB)")
    print(f"Try: python main.py {out} --skip-epub --max-pages 1")


if __name__ == "__main__":
    main()
