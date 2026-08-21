"""Isolated Docling worker, launched with a timeout by the main CLI."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise SystemExit(
            "Docling is not installed. Install the optional 'documents' extra."
        ) from exc

    result = DocumentConverter().convert(str(args.source))
    markdown = result.document.export_to_markdown()
    args.output.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
