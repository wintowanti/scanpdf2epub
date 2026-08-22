#!/usr/bin/env python3
"""Unified CLI: PDF -> Markdown -> EPUB, one book or a whole directory.

Wraps the two-stage pipeline behind a single entry point:

    stage 1  paddle_convert.py   PDF -> Markdown (+ imgs/)   (PaddleOCR layout)
    stage 2  build_epub.py       Markdown -> EPUB            (ebooklib)

Both stages stay individually runnable; ``--skip-md`` / ``--skip-epub`` let
you run either one alone. The two-stage workflow was designed to be decoupled:
OCR everything to Markdown, proofread/fix by hand, then rebuild the EPUB.

Usage examples:
  python main.py book.pdf                      # full pipeline, one book
  python main.py ./books/                      # full pipeline, every PDF in dir
  python main.py ./input/ --skip-epub          # OCR only, no EPUB
  python main.py book.pdf --skip-md            # rebuild EPUB from existing Markdown
  python main.py book.pdf --start-page 10 --max-pages 20   # just a few pages
"""
import argparse
import sys
from pathlib import Path

import paddle_convert
import build_epub


def _collect_pdfs(input_path):
    """Return the sorted list of PDFs to process from a file/dir argument.

    With no argument, default to ``./input/`` (created if missing) — drop
    PDFs there and run ``python main.py`` for a simple batch workflow.
    """
    if input_path is None:
        d = Path.cwd() / "input"
        d.mkdir(exist_ok=True)
        pdfs = sorted(d.glob("*.pdf"))
        if not pdfs:
            print(f"No PDF files found in default input directory: {d}", file=sys.stderr)
            sys.exit(1)
        return pdfs

    p = Path(input_path)
    if p.is_dir():
        pdfs = sorted(p.glob("*.pdf"))
        if not pdfs:
            print(f"No PDF files found in directory: {p}", file=sys.stderr)
            sys.exit(1)
        return pdfs
    if p.is_file():
        if p.suffix.lower() != ".pdf":
            print(f"Error: input must be a PDF file: {p}", file=sys.stderr)
            sys.exit(1)
        return [p]
    print(f"Error: input path does not exist: {p}", file=sys.stderr)
    sys.exit(1)


def _announce_device():
    """Print whether Paddle runs on GPU or CPU (lazy: only once OCR starts)."""
    try:
        import paddle
    except ImportError:
        print("PaddlePaddle is not installed — follow the install steps in the README.", file=sys.stderr)
        raise
    if paddle.device.is_compiled_with_cuda():
        print("Paddle: GPU (CUDA) — using GPU.", flush=True)
    else:
        print("Paddle: CPU — OCR will be slow; install paddlepaddle-gpu for speed.", flush=True)


def build_arg_parser():
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="Convert scanned (Simplified Chinese) PDF books to Markdown and EPUB.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "input", nargs="?", default=None,
        help="PDF file, or directory of PDFs (default: ./input/)",
    )
    ap.add_argument(
        "output", nargs="?", default=None,
        help="output directory for Markdown/images (default: <stem>/ next to each PDF)",
    )

    stage = ap.add_argument_group("stage control (two-stage pipeline)")
    stage.add_argument(
        "--skip-epub", action="store_true",
        help="run stage 1 only: PDF -> Markdown, no EPUB",
    )
    stage.add_argument(
        "--skip-md", action="store_true",
        help="run stage 2 only: build EPUB from existing Markdown",
    )

    ocr = ap.add_argument_group("stage 1 — OCR (PaddleOCR)")
    ocr.add_argument("--start-page", type=int, default=0, help="first page index (0-based)")
    ocr.add_argument("--max-pages", type=int, default=None, help="maximum number of pages to convert")
    ocr.add_argument(
        "--dpi", type=int, default=200,
        help="render resolution; lower is faster, raise it again if small text drops out",
    )
    ocr.add_argument(
        "--lang", default="ch",
        help="PaddleOCR recognition language code. The post-processing heuristics "
             "in paddle_convert.py are tuned for Simplified Chinese prose; other "
             "languages run but without those repairs.",
    )

    epub = ap.add_argument_group("stage 2 — EPUB metadata (optional)")
    epub.add_argument("--title", default=None)
    epub.add_argument("--author", default=None)
    epub.add_argument("--publisher", default=None)
    epub.add_argument("--isbn", default=None)
    epub.add_argument("--epub-language", default="zh", help="EPUB <dc:language> value")
    return ap


def main():
    args = build_arg_parser().parse_args()
    pdfs = _collect_pdfs(args.input)

    if args.skip_md and args.skip_epub:
        print("Error: --skip-md and --skip-epub together do nothing.", file=sys.stderr)
        sys.exit(1)
    if args.skip_md:
        plan = "MD -> EPUB only (using existing Markdown)"
    elif args.skip_epub:
        plan = "PDF -> MD only"
    else:
        plan = "PDF -> MD -> EPUB"
    print(f"Found {len(pdfs)} PDF file(s) to process. Plan: {plan}")

    failed = []
    for pdf_path in pdfs:
        print(f"\n===== {pdf_path.name} =====", flush=True)
        try:
            md_dir = Path(args.output) if args.output else pdf_path.parent / pdf_path.stem
            md_path = md_dir / f"{pdf_path.stem}.md"

            if args.skip_md and not md_path.exists():
                print(f"Error: no Markdown found at {md_path} — run without --skip-md first.",
                      file=sys.stderr)
                failed.append(pdf_path.name)
                continue

            if not args.skip_md:
                _announce_device()
                md_path = paddle_convert.convert_pdf(
                    pdf_path, md_dir, args.start_page, args.max_pages, args.dpi, args.lang,
                )

            if not args.skip_epub:
                epub_path = (md_dir if args.output else pdf_path.parent) / f"{pdf_path.stem}.epub"
                base = build_epub.infer_metadata(md_path)
                meta = {
                    "title": args.title or base["title"],
                    "author": args.author or base["author"],
                    "publisher": args.publisher or base["publisher"],
                    "isbn": args.isbn or base["isbn"],
                    "language": args.epub_language,
                }
                print("Building EPUB...", flush=True)
                build_epub.build(pdf_path, md_path, epub_path, meta)

        except Exception as e:
            print(f"Error processing {pdf_path.name}: {e}", file=sys.stderr)
            failed.append(pdf_path.name)
            continue

    if failed:
        print(f"\nFailed to process {len(failed)} of {len(pdfs)} PDF file(s):", file=sys.stderr)
        for name in failed:
            print(f"  - {name}", file=sys.stderr)
        sys.exit(1)
    print("\nAll done.")


if __name__ == "__main__":
    main()
