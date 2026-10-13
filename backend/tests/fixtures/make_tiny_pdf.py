"""Generate the committed ``tests/fixtures/tiny.pdf`` fixture.

Run once from ``backend/`` with the shared venv python; the output is committed
so parser tests and the browser upload flow always use the same minimal file.
"""

from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent / "tiny.pdf"

CONTENT_STREAM = b"BT /F1 12 Tf 72 720 Td (Stub fixture paragraph.) Tj ET"


def _build_pdf() -> bytes:
    """Return the bytes of a minimal single-page PDF containing one text line."""

    object_bodies = [
        # Object 1: catalog, the document root every reader starts from.
        b"<< /Type /Catalog /Pages 2 0 R >>",
        # Object 2: the page tree holding the single page.
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        # Object 3: the page, drawing its content from object 4 with font object 5.
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        # Object 4: the content stream, with /Length counting exactly its bytes.
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(CONTENT_STREAM), CONTENT_STREAM),
        # Object 5: the standard Type1 font referenced as /F1 by the content stream.
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    parts: list[bytes] = [b"%PDF-1.4\n"]
    offsets: list[int] = []
    position = len(parts[0])
    for number, body in enumerate(object_bodies, start=1):
        block = b"%d 0 obj\n%s\nendobj\n" % (number, body)
        offsets.append(position)
        parts.append(block)
        position += len(block)
    xref_position = position
    entries = [b"0000000000 65535 f "]
    entries += [b"%010d 00000 n " % offset for offset in offsets]
    parts.append(b"xref\n0 %d\n" % (len(object_bodies) + 1))
    parts += [entry + b"\n" for entry in entries]
    trailer = b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(object_bodies) + 1,
        xref_position,
    )
    parts.append(trailer)
    return b"".join(parts)


def main() -> None:
    """Write the tiny PDF fixture next to this script."""

    FIXTURE_PATH.write_bytes(_build_pdf())


if __name__ == "__main__":
    main()
