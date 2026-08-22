#!/usr/bin/env python3
"""PaddleOCR-based PDF -> Markdown converter (replaces slow marker-pdf OCR path).

Usage:
  .venv-paddle/bin/python paddle_convert.py <pdf> [--max-pages N] [--start-page N] [--dpi 200]
"""
import argparse
import re
from pathlib import Path

import pypdfium2 as pdfium
import numpy as np
from PIL import Image

# Blocks whose content is a figure/image region we can crop from the page.
VISION_LABELS = {"image", "figure", "chart", "flowchart", "picture"}


# ---- Post-processing: repair common OCR/layout artifacts in the markdown ----

# Characters that end a sentence/paragraph in Chinese prose. Lines ending in
# anything else are treated as mid-paragraph, so a following line that starts
# with CJK/letter is a continuation (the layout model split one paragraph into
# several blocks and inserted a blank line between them).
_SENT_ENDERS = set("。！？…」』）】\"”’'!?")


def _is_cjk_or_letter(ch):
    return "一" <= ch <= "鿿" or ch.isalpha()


def _is_struct_line(line):
    """Markdown structural line: heading, list, quote, code, image, table..."""
    s = line.strip()
    if not s:
        return True
    if s.startswith(("#", "-", "*", ">", "|", "```", "![", "<div", "<table", "$$")):
        return True
    return bool(re.match(r"^\d+[.、]", s))


def _looks_role_entry(line):
    """Line like '作者/张小满' or '出版统筹_杨静武' — a key/value list entry."""
    return bool(re.search(r"[/／_]", line[:10]))


def _should_merge(prev, nxt):
    """True if `nxt` continues the paragraph `prev` (blank line between them is spurious)."""
    prev = prev.rstrip()
    nxt = nxt.strip()
    if not prev or not nxt:
        return False
    if _is_struct_line(prev) or _is_struct_line(nxt):
        return False
    # paragraph break if prev ends with a sentence-ender
    if prev[-1] in _SENT_ENDERS:
        return False
    # TOC / list guards: page-number-ish lines are never merged across
    if prev[-1].isdigit() or nxt[0].isdigit() or nxt[-1].isdigit():
        return False
    # key/value role lines (copyright page) are separate entries
    if _looks_role_entry(prev):
        return False
    # cover junk: two adjacent short fragments are separate decorations
    if len(prev) <= 6 and len(nxt) <= 6:
        return False
    # continuation must start with CJK/letter (not punctuation/quote) so we
    # don't swallow dialogue lines that start with a quotation mark
    if not _is_cjk_or_letter(nxt[0]):
        return False
    return True


def fix_paragraph_breaks(md):
    """Collapse blank lines that fall in the middle of a paragraph."""
    lines = md.split("\n")
    result = []
    for line in lines:
        if line.strip() == "":
            result.append("")
            continue
        if result and result[-1] == "":
            prev = None
            for k in range(len(result) - 2, -1, -1):
                if result[k].strip():
                    prev = result[k]
                    break
            if prev is not None and _should_merge(prev, line):
                result.pop()  # drop the blank line
                result[-1] = result[-1].rstrip() + line  # stitch the split line
                continue
        result.append(line)
    return "\n".join(result)


def _circled(m):
    """\\textcircled{1} -> ①, \\textcircled{a} -> ⓐ, etc."""
    ch = m.group(1)
    if ch.isdigit():
        return "①②③④⑤⑥⑦⑧⑨"[int(ch) - 1] if 1 <= int(ch) <= 9 else ch
    if "a" <= ch <= "z":
        return chr(0x24B6 + ord(ch) - ord("a"))
    return ch


def fix_latex(md):
    """Clean formula-recognition noise out of prose.

    - any ``$...\\times...$`` is the redacted name ×× (this memoir has no real
      math), so collapse each ``$...$`` to as many × as it contained;
    - footnote superscripts ``\\mathrm{VP}^{\\textcircled{1}}`` -> ``VP①``;
    - drop remaining LaTeX sigils (``$`` ``^`` braces).
    """
    md = re.sub(
        r"\$([^$]*\\times[^$]*)\$",
        lambda m: "×" * max(1, m.group(1).count("\\times")),
        md,
    )
    md = re.sub(r"\\textcircled\{([0-9a-z])\}", _circled, md)
    md = re.sub(r"\\mathrm\{([A-Za-z ]+)\}", r"\1", md)
    md = md.replace("$", "").replace("^", "").replace("{", "").replace("}", "")
    # clean OCR spacing artifacts left around the restored ××
    md = re.sub(r"×\s*[,，]", "×，", md)
    md = re.sub(r"×\s*\[", "×“", md)
    return md


def remove_noise_heads(md):
    """Drop decorative divider headings like '## ***' that carry no text."""
    return re.sub(r"^#{1,3}\s*\*+\s*$", "", md, flags=re.M)


def fix_markdown(md):
    md = fix_latex(md)
    md = fix_paragraph_breaks(md)
    md = remove_noise_heads(md)
    return md


def render_pages(pdf_path: str, start: int, count: int, dpi: int):
    pdf = pdfium.PdfDocument(pdf_path)
    total = len(pdf)
    end = min(start + count, total) if count else total
    pages = list(range(start, end))
    imgs = []
    for idx in pages:
        pil = pdf[idx].render(scale=dpi / 72).to_pil().convert("RGB")
        imgs.append(np.array(pil))
    return imgs, pages, total


def build_pipeline(device_batch=16, lang="ch"):
    from paddleocr import PPStructureV3

    return PPStructureV3(
        lang=lang,
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
        use_textline_orientation=True,
        use_table_recognition=True,
        use_formula_recognition=True,
        format_block_content="markdown",
        text_recognition_batch_size=device_batch,
        text_det_limit_side_len=1920,
        text_det_limit_type="max",
    )


def crop_images_from_markdown(page_md, page_img, img_dir: Path):
    """Crop embedded-image regions referenced by the page's markdown.

    paddlex names nested images ``imgs/img_in_image_box_<x1>_<y1>_<x2>_<y2>.jpg``
    where the numbers are the block bbox in page-pixel space, so we can crop
    straight from the filename without touching the (often empty) block content.
    """
    h, w = page_img.shape[:2]
    for m in re.finditer(r"img_in_image_box_(\d+)_(\d+)_(\d+)_(\d+)\.jpg", page_md):
        x1, y1, x2, y2 = (int(v) for v in m.groups())
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = Image.fromarray(page_img[y1:y2, x1:x2])
        fname = m.group(0)
        (img_dir / fname).parent.mkdir(parents=True, exist_ok=True)
        crop.save(img_dir / fname)
        print(f"  saved image: imgs/{fname}", flush=True)


def convert_pdf(pdf_path, out_dir, start_page=0, max_pages=None, dpi=200, lang="ch", device_batch=16):
    """Convert one PDF to Markdown (+ imgs/) under `out_dir`.

    Returns the path of the produced Markdown file. Pulled out of ``main()``
    so the unified ``main.py`` CLI can drive the pipeline in-process.
    """
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{pdf_path.stem}.md"
    img_dir = out_dir / "imgs"

    pdf = pdfium.PdfDocument(str(pdf_path))
    total = len(pdf)
    end = min(start_page + (max_pages or total - start_page), total)
    n_pages = end - start_page
    print(f"Converting {n_pages} pages (PDF total: {total}): page idx {start_page}-{end-1}", flush=True)

    print("Building PPStructureV3 pipeline...", flush=True)
    pipeline = build_pipeline(device_batch=device_batch, lang=lang)

    # Render + process in chunks so RAM stays bounded (370 @ 200DPI ≈ 4.6GB).
    all_md_parts = []
    CHUNK = 16  # pages rendered at once
    BATCH = 4   # pages fed to pipeline.predict per call
    n_chunks = (n_pages + CHUNK - 1) // CHUNK
    for c in range(n_chunks):
        idxs = list(range(start_page + c * CHUNK, min(start_page + (c + 1) * CHUNK, end)))
        imgs = [
            np.array(pdf[i].render(scale=dpi / 72).to_pil().convert("RGB"))
            for i in idxs
        ]
        print(f"  chunk {c+1}/{n_chunks}: pages {idxs[0]}-{idxs[-1]}", flush=True)
        for b in range(0, len(imgs), BATCH):
            batch = imgs[b : b + BATCH]
            print(f"    batch {b//BATCH + 1}/{(len(imgs)+BATCH-1)//BATCH}", flush=True)
            results = pipeline.predict(batch, format_block_content="markdown")
            for page_img, res in zip(batch, results):
                md_info = res._to_markdown()
                page_md = md_info.get("markdown_texts") or ""
                crop_images_from_markdown(page_md, page_img, img_dir)
                all_md_parts.append(page_md)
        del imgs  # free chunk

    print("Saving markdown...", flush=True)
    full_md = fix_markdown("\n\n".join(all_md_parts))
    md_path.write_text(full_md, encoding="utf-8")
    print(f"Markdown saved to: {md_path} ({len(full_md)} chars)", flush=True)
    return md_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--start-page", type=int, default=0)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--lang", default="ch", help="PaddleOCR recognition language (default: ch)")
    ap.add_argument("--output", default=None, help="output directory (default: <stem>/ next to pdf)")
    args = ap.parse_args()

    out_dir = Path(args.output) if args.output else Path(args.pdf).with_suffix("")
    convert_pdf(args.pdf, out_dir, args.start_page, args.max_pages, args.dpi, args.lang)


if __name__ == "__main__":
    main()
