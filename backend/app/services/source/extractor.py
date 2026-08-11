import re
from docx import Document as DocxDocument
from lxml import html as lxml_html
from pypdf import PdfReader

URL_RE = re.compile(
    r'https?://[^\s]+?(?=[\s\]\)\},;.!?]|$)'
)
URL_LIKE_RE = re.compile(
    r'[\w\W]{0,8}://[^\s]+?(?=[\s\]\)\},;.!?]|$)'
)
DRIVE_FILE_ID_RE = re.compile(
    r'drive\.google\.com/(?:file/d/|open\?id=|uc\?id=|document/d/)([A-Za-z0-9_-]+)',
    re.IGNORECASE,
)

def _extract_links_from_text(text: str) -> list[str]:
    text = _normalize_ocr_text(text)
    links = []
    for match in URL_RE.finditer(text):
        links.append(_repair_url_candidate(match.group()))

    if not links:
        for match in URL_LIKE_RE.finditer(text):
            repaired = _repair_url_candidate(match.group())
            if repaired:
                links.append(repaired)

    links.extend(_extract_drive_links(text))
    return links


def _normalize_ocr_text(text: str) -> str:
    text = text.translate(str.maketrans({
        "ﬁ": "fi",
        "ﬂ": "fl",
        "…": "...",
    }))
    text = text.replace("hƩps://", "https://")
    text = text.replace("hΤps://", "https://")
    text = text.replace("hтtps://", "https://")
    text = text.replace("hps://", "https://")
    text = text.replace("httрs://", "https://")
    text = re.sub(r"https?\s*:\s*//", "https://", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=https://)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=drive\.google\.com)/\s+", "/", text, flags=re.IGNORECASE)
    return text


def _repair_url_candidate(candidate: str) -> str:
    candidate = _normalize_ocr_text(candidate).strip()
    candidate = candidate.rstrip(".,;:!?)]}")
    if "://" not in candidate:
        return candidate

    scheme, rest = candidate.split("://", 1)
    scheme_ascii = re.sub(r"[^a-z]", "", scheme.lower())
    if scheme_ascii in {"http", "https", "hps", "htps", "hpps", "hptps"}:
        return f"https://{rest}"
    if scheme_ascii.startswith("h") and scheme_ascii.endswith("ps"):
        return f"https://{rest}"
    return candidate


def _extract_drive_links(text: str) -> list[str]:
    normalized = _normalize_ocr_text(text)
    links: list[str] = []
    for match in DRIVE_FILE_ID_RE.finditer(normalized):
        file_id = match.group(1)
        links.append(f"https://drive.google.com/file/d/{file_id}/view?usp=sharing")

    if "drive.google.com" in normalized:
        compact = re.sub(r"\s+", "", normalized)
        match = re.search(
            r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=|document/d/)([A-Za-z0-9_-]+)",
            compact,
            re.IGNORECASE,
        )
        if match:
            file_id = match.group(1)
            links.append(f"https://drive.google.com/file/d/{file_id}/view?usp=sharing")

    return list(dict.fromkeys(links))


def _extract_pdf_links(reader: PdfReader, text: str) -> list[str]:
    links = _extract_links_from_text(text)
    for page in reader.pages:
        annotations = page.get("/Annots") or []
        for annotation in annotations:
            try:
                obj = annotation.get_object()
                action = obj.get("/A") or {}
                uri = action.get("/URI")
                if uri:
                    links.append(str(uri).rstrip(".,;:!?)]}"))
            except Exception:
                continue
    return list(dict.fromkeys(links))


def _extract_docx_links(file_obj) -> tuple[int, list[str]]:
    file_obj.seek(0)
    doc = DocxDocument(file_obj)
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    links = _extract_links_from_text(text)
    for rel in doc.part.rels.values():
        if rel.reltype.endswith("/hyperlink") and rel.target_ref:
            links.append(str(rel.target_ref).rstrip(".,;:!?)]}"))
    return 1, list(dict.fromkeys(links))


def _extract_html_links(html_text: str) -> list[str]:
    try:
        tree = lxml_html.fromstring(html_text)
    except Exception:
        return _extract_links_from_text(html_text)

    links = _extract_links_from_text(html_text)
    for href in tree.xpath("//a/@href | //@src"):
        href = str(href).strip()
        if href.startswith(("http://", "https://")):
            links.append(href.rstrip(".,;:!?)]}"))
    return list(dict.fromkeys(links))
