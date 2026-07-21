"""Bounded document validation, parsing, normalization, chunking, and storage."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePath
from uuid import uuid4

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.config import Settings

SUPPORTED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class DocumentError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPart:
    text: str
    page_number: int | None = None
    section: str | None = None


def _markdown_parts(text: str) -> list[ExtractedPart]:
    parts: list[ExtractedPart] = []
    section: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            value = normalize_text("\n".join(body))
            if value:
                parts.append(ExtractedPart(value, section=section))
            section, body = heading.group(1)[:255], []
        else:
            body.append(line)
    value = normalize_text("\n".join(body))
    if value:
        parts.append(ExtractedPart(value, section=section))
    return parts


def validate_upload(filename: str, media_type: str, content: bytes, settings: Settings) -> str:
    clean = PurePath(filename).name
    if not clean or clean != filename or "\x00" in filename:
        raise DocumentError("Invalid filename")
    suffix = Path(clean).suffix.casefold()
    if suffix not in SUPPORTED:
        raise DocumentError("Unsupported file extension")
    allowed = {SUPPORTED[suffix]}
    if suffix == ".md":
        allowed.add("text/plain")
    if media_type.casefold().split(";", 1)[0] not in allowed:
        raise DocumentError("File type does not match extension")
    if not content or len(content) > settings.document_max_bytes:
        raise DocumentError("File is empty or exceeds the configured size limit")
    signatures = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04"}
    if suffix in signatures and not content.startswith(signatures[suffix]):
        raise DocumentError("Detected file content does not match extension")
    if suffix in {".txt", ".md"} and b"\x00" in content:
        raise DocumentError("Detected binary content in text document")
    return clean


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract(content: bytes, suffix: str, settings: Settings) -> list[ExtractedPart]:
    try:
        if suffix == ".pdf":
            reader = PdfReader(io.BytesIO(content), strict=True)
            if len(reader.pages) > settings.document_max_pages:
                raise DocumentError("PDF page limit exceeded")
            parts = [
                ExtractedPart(normalize_text(page.extract_text() or ""), i + 1)
                for i, page in enumerate(reader.pages)
            ]
        elif suffix == ".docx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if len(archive.infolist()) > 10_000 or any(
                    item.flag_bits & 0x1 for item in archive.infolist()
                ):
                    raise DocumentError("DOCX archive limits exceeded")
                total = sum(item.file_size for item in archive.infolist())
                if total > settings.document_max_extracted_chars * 4:
                    raise DocumentError("DOCX decompression limit exceeded")
            doc = DocxDocument(io.BytesIO(content))
            parts = []
            section: str | None = None
            body: list[str] = []
            for paragraph in doc.paragraphs:
                if paragraph.style.name.casefold().startswith("heading"):
                    value = normalize_text("\n".join(body))
                    if value:
                        parts.append(ExtractedPart(value, section=section))
                    section, body = paragraph.text[:255], []
                else:
                    body.append(paragraph.text)
            value = normalize_text("\n".join(body))
            if value:
                parts.append(ExtractedPart(value, section=section))
        elif suffix == ".md":
            parts = _markdown_parts(content.decode("utf-8", errors="strict"))
        else:
            parts = [ExtractedPart(normalize_text(content.decode("utf-8", errors="strict")))]
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("Document could not be safely parsed") from exc
    if sum(len(part.text) for part in parts) > settings.document_max_extracted_chars:
        raise DocumentError("Extracted text limit exceeded")
    if not any(part.text for part in parts):
        raise DocumentError("Document contains no extractable text")
    return parts


def chunk_parts(parts: list[ExtractedPart], size: int, overlap: int) -> list[ExtractedPart]:
    chunks: list[ExtractedPart] = []
    step = size - overlap
    for part in parts:
        for start in range(0, len(part.text), step):
            value = part.text[start : start + size].strip()
            if value:
                chunks.append(ExtractedPart(value, part.page_number, part.section))
            if start + size >= len(part.text):
                break
    return chunks


def store(content: bytes, root: str) -> tuple[str, str]:
    key = f"{uuid4().hex[:2]}/{uuid4().hex}"
    target = Path(root).resolve() / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return key, hashlib.sha256(content).hexdigest()


def load(root: str, key: str) -> bytes:
    root_path = Path(root).resolve()
    target = (root_path / key).resolve()
    if root_path not in target.parents:
        raise DocumentError("Invalid storage key")
    return target.read_bytes()


def remove(root: str, key: str) -> None:
    root_path = Path(root).resolve()
    target = (root_path / key).resolve()
    if root_path in target.parents:
        target.unlink(missing_ok=True)
