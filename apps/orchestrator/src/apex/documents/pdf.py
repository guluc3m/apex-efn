"""A tiny deterministic text-PDF writer: Helvetica, A4, uncompressed, no dependency.

Same input, same bytes (no clock, no random ids), so a document's SHA-256 can be recomputed and stored.
# ponytail: Latin-1 text only (other characters print as "?"). Switch to reportlab with an embedded font
# if a document ever has to show Chinese seller names.
"""

from __future__ import annotations

import textwrap

_LINES_PER_PAGE = 58
_WIDTH = 92


def _escape(text: str) -> str:
    safe = text.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pages(lines: list[str]) -> list[list[str]]:
    wrapped = [part for line in lines for part in (textwrap.wrap(line, _WIDTH) or [""])]
    return [wrapped[i : i + _LINES_PER_PAGE] for i in range(0, len(wrapped), _LINES_PER_PAGE)] or [
        []
    ]


def text_pdf(title: str, lines: list[str], *, trailer_comment: bytes = b"") -> bytes:
    """``lines`` are laid out top to bottom. ``trailer_comment`` is a single-line PDF comment appended last."""
    pages = _pages(lines)
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, page in enumerate(pages):
        body = [
            "BT",
            "/F1 9 Tf",
            "12 TL",
            "50 800 Td",
            f"({_escape(title)}) Tj" if i == 0 else "() Tj",
        ]
        body += [f"T* ({_escape(line)}) Tj" for line in page]
        body.append("ET")
        stream = "\n".join(body).encode("latin-1")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
            + f"/Contents {5 + 2 * i} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    if trailer_comment:
        out += b"%" + trailer_comment + b"\n"
    return bytes(out)
