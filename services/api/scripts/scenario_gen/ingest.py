"""Load a PDF (local path or http(s) URL) into Anthropic message content."""

from __future__ import annotations

import base64
import urllib.request
from pathlib import Path

# Above this size we extract text with pypdf instead of sending the raw PDF
# (base64 document blocks are ~33% larger and large PDFs blow the context).
MAX_PDF_BYTES = 24 * 1024 * 1024
MAX_TEXT_CHARS = 120_000


def _read_source(source: str) -> bytes:
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": "scenario-gen"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - user-supplied
            return resp.read()
    data = Path(source).read_bytes()
    if not data:
        raise ValueError(f"PDF is empty: {source}")
    return data


def _extract_text(pdf_bytes: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
        if sum(len(p) for p in parts) >= MAX_TEXT_CHARS:
            break
    text = "\n\n".join(parts).strip()
    return text[:MAX_TEXT_CHARS]


def load_pdf_blocks(source: str) -> list[dict]:
    """Return user-message content blocks representing the PDF.

    Small PDFs are sent as a native ``document`` block (preserves layout/figures);
    large ones are downsampled to extracted text.
    """
    pdf_bytes = _read_source(source)

    if len(pdf_bytes) <= MAX_PDF_BYTES:
        b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
        return [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            }
        ]

    text = _extract_text(pdf_bytes)
    if not text:
        raise ValueError(
            "PDF is too large to send and no extractable text was found."
        )
    return [
        {
            "type": "text",
            "text": f"(Source document, text-extracted)\n\n{text}",
        }
    ]
