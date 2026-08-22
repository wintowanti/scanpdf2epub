#!/usr/bin/env python3
"""Build a Chinese-typeset EPUB from the PaddleOCR markdown output.

Reads the full-book .md next to the PDF, renders PDF page 0 as the cover,
splits the book into parts/chapters, and packs an EPUB3 with ebooklib.
"""
import argparse
import re
from pathlib import Path

import markdown as mdlib
import pypdfium2 as pdfium
from ebooklib import epub

VISION_IMG = re.compile(r'src="imgs/([^"]+\.jpg)"')

CSS = """
@page { margin: 6pt 8pt; }
body {
    font-family: "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", "SimSun", serif;
    font-size: 1.0em;
    line-height: 1.85;
    text-align: justify;
    margin: 0.4em 1em;
    color: #222;
}
p {
    text-indent: 2em;
    margin: 0 0 0 0;
    orphans: 2;
    widows: 2;
}
h1, h2, h3 {
    text-align: center;
    line-height: 1.4;
    font-weight: bold;
}
h1 { font-size: 1.55em; margin: 1.6em 0 1.2em; }
h2 { font-size: 1.3em;  margin: 1.9em 0 1.3em; }
h3 { font-size: 1.12em; margin: 1.6em 0 1em; }
blockquote {
    margin: 0.8em 1em;
    padding: 0 0.8em;
    color: #444;
    border-left: 3px solid #bbb;
}
ul, ol { padding-left: 2em; margin: 0.5em 0; }
li { margin: 0.2em 0; }
hr { border: none; border-top: 1px solid #999; margin: 1.5em 0; }
div { margin: 1em 0; }
.title-page { text-align: center; padding-top: 4em; }
.title-page .t1 { font-size: 2.2em; letter-spacing: 0.2em; }
.title-page .t2 { font-size: 1.1em; margin-top: 2.5em; }
.title-page .t3 { font-size: 0.9em; margin-top: 5em; color: #555; }
"""


def render_cover(pdf_path: str, width: int = 1200) -> bytes:
    """Render PDF page 0 as the cover, scaled to ~width px, return JPEG bytes."""
    pdf = pdfium.PdfDocument(pdf_path)
    scale = width / pdf[0].get_size()[0]
    pil = pdf[0].render(scale=scale).to_pil().convert("RGB")
    import io

    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def parse_sections(md: str):
    """Split markdown into {'level','title','body':[lines]} sections.

    Skips the physical-cover OCR garbage and the title page before the first
    ``##``, and drops the markdown's own 目录 (the EPUB nav replaces it).
    """
    sections = []
    cur = None
    started = False
    for ln in md.split("\n"):
        m1 = re.match(r"^# (.+)$", ln)
        m2 = re.match(r"^## (.+)$", ln)
        m3 = re.match(r"^### (.+)$", ln)
        if m1 or m2 or m3:
            if not started and (m2 or m3):
                # reached the real front matter; the cover page + title page
                # (`# 大厂小民` and everything before) is skipped
                started = True
            elif not started:
                continue  # still in cover/title-page region
            if m3 and cur is not None:
                # sub-heading (e.g. CIP's '### I. I25') stays inside its section
                cur["body"].append(ln)
                continue
            if cur is not None:
                sections.append(cur)
            cur = {
                "level": 1 if m1 else 2,
                "title": (m1 or m2).group(1).strip(),
                "body": [],
            }
        elif cur is not None:
            cur["body"].append(ln)
    if cur is not None:
        sections.append(cur)
    # drop the markdown's own 目录
    return [s for s in sections if s["title"] != "目录"]


def md_to_html(fragment: str) -> str:
    """Convert a section body (markdown lines) to inner HTML."""
    text = "\n".join(fragment)
    return mdlib.markdown(text, extensions=["markdown.extensions.nl2br"])


def add_chapter(book, name: str, title: str, inner_html: str, css_href: str, lang: str):
    """Create an EpubHtml chapter and register it; return the item.

    NOTE: content must NOT start with an ``<?xml ...?>`` declaration — ebooklib
    parses ``self.content`` with lxml.html, which refuses unicode strings that
    carry an encoding declaration, silently returning empty content.
    """
    page = epub.EpubHtml(uid=name, title=title, file_name=name, lang=lang)
    page.content = (
        f'<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        f'<link rel="stylesheet" type="text/css" href="{css_href}"/>'
        f'<title>{title}</title></head><body>{inner_html}</body></html>'
    )
    book.add_item(page)
    return page


def infer_metadata(md_path: Path):
    """Guess book metadata from the markdown's first ``# `` heading."""
    md = md_path.read_text(encoding="utf-8")
    m = re.search(r"^# (.+)$", md, re.M)
    title = m.group(1).strip() if m else md_path.stem
    return {"title": title, "author": "", "publisher": "", "isbn": ""}


def build(pdf_path: Path, md_path: Path, out_path: Path, meta: dict | None = None):
    md = md_path.read_text(encoding="utf-8")
    sections = parse_sections(md)

    m = meta or infer_metadata(md_path)
    title = m["title"]
    author = m.get("author") or ""
    publisher = m.get("publisher") or ""
    isbn = m.get("isbn") or str(abs(hash(str(pdf_path) + title)))
    lang = m.get("language") or "zh"

    book = epub.EpubBook()
    book.set_identifier(isbn)
    book.set_title(title)
    book.set_language(lang)
    if author:
        book.add_author(author)
    if publisher:
        book.add_metadata("DC", "publisher", publisher)

    # --- cover ---
    cover_bytes = render_cover(str(pdf_path))
    book.add_item(epub.EpubImage(
        uid="cover-img", file_name="images/cover.jpg",
        media_type="image/jpeg", content=cover_bytes,
    ))
    book.add_metadata(None, "meta", "", {"name": "cover", "content": "cover-img"})
    cover_page = epub.EpubHtml(uid="cover.xhtml", title="封面", file_name="cover.xhtml", lang=lang)
    cover_page.content = (
        f'<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        f'<link rel="stylesheet" type="text/css" href="style/style.css"/>'
        f'<title>{title}</title></head><body>'
        f'<div style="text-align:center;margin:0;padding:0;">'
        f'<img src="images/cover.jpg" style="width:100%;height:auto;"/></div>'
        f'</body></html>'
    )
    book.add_item(cover_page)
    cover_name = cover_page.file_name

    # --- css ---
    css_item = epub.EpubItem(
        uid="style", file_name="style/style.css",
        media_type="text/css", content=CSS.encode("utf-8"),
    )
    book.add_item(css_item)

    # --- images referenced by the body ---
    image_names = set()
    for s in sections:
        image_names |= set(VISION_IMG.findall("\n".join(s["body"])))
    img_href = {}
    for name in sorted(image_names):
        src = (md_path.parent / "imgs" / name).read_bytes()
        img_href[name] = f"images/{name}"
        book.add_item(epub.EpubItem(
            uid=f"img_{name}", file_name=f"images/{name}",
            media_type="image/jpeg", content=src,
        ))

    # --- title page ---
    title_page = epub.EpubHtml(
        uid="titlepage", title=title, file_name="titlepage.xhtml", lang=lang)
    title_page.content = (
        f'<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        f'<link rel="stylesheet" type="text/css" href="style/style.css"/>'
        f'<title>{title}</title></head><body>'
        f'<div class="title-page"><div class="t1">{title}</div>'
        f'<div class="t2">{author + " 著" if author else ""}</div>'
        f'<div class="t3">{publisher}</div></div>'
        f'</body></html>'
    )
    book.add_item(title_page)

    # --- body: front matter, preface, parts, chapters ---
    toc = []
    spine = [cover_name, "titlepage", "nav"]
    part_section = None
    part_links = []

    def flush_part():
        nonlocal part_section, part_links
        if part_section is not None:
            toc.append((epub.Section(part_section), tuple(part_links)))
        part_section, part_links = None, []

    for s in sections:
        inner = md_to_html(s["body"])
        inner = VISION_IMG.sub(lambda m: f'src="{img_href[m.group(1)]}"', inner)
        level = s["level"]
        title = s["title"]

        if level == 1:
            flush_part()
            part_section = title
            continue
        # level 2/3 -> chapter
        name = f"ch_{len(spine):03d}.xhtml"
        add_chapter(book, name, title, inner, "style/style.css", lang)
        spine.append(name)
        link = epub.Link(name, title, f"sec_{len(spine)}")
        if part_section is not None:
            part_links.append(link)
        else:
            toc.append(link)

    flush_part()

    # front-matter chapters (CIP / author bio) landed in `toc` before 前言;
    # everything is already ordered correctly.

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(out_path), book, {})
    print(f"EPUB written: {out_path} ({out_path.stat().st_size/1024:.0f} KB)")
    print(f"  chapters: {len(spine)-2}, images: {len(image_names)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build a Chinese-typeset EPUB from a PaddleOCR markdown + the source PDF.")
    ap.add_argument("pdf")
    ap.add_argument("--md", default=None, help="markdown file (default: <pdf_stem>/<pdf_stem>.md next to the pdf)")
    ap.add_argument("--output", default=None, help="output epub path (default: <pdf>.epub)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--author", default=None)
    ap.add_argument("--publisher", default=None)
    ap.add_argument("--isbn", default=None)
    ap.add_argument("--language", default="zh")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    md = Path(args.md) if args.md else pdf.parent / pdf.stem / f"{pdf.stem}.md"
    out = Path(args.output) if args.output else pdf.parent / f"{pdf.stem}.epub"

    base = infer_metadata(md)
    meta = {
        "title": args.title or base["title"],
        "author": args.author or base["author"],
        "publisher": args.publisher or base["publisher"],
        "isbn": args.isbn or base["isbn"],
        "language": args.language,
    }
    build(pdf, md, out, meta)
