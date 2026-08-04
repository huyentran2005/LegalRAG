"""
Parser cấu trúc phân cấp cho văn bản luật Việt Nam:
Chương -> Điều -> Khoản (-> Điểm, xử lý ở tầng chunking).
"""
import re
from dataclasses import dataclass, field

from rag.service.text import normalize

CHUONG_RE = re.compile(r'^Chương\s+([IVXLCDM]+)\.?\s*(.*)$') # type: ignore
DIEU_RE = re.compile(r'^Điều\s+(\d+)\.\s*(.*)$')
KHOAN_RE = re.compile(r'^(\d+)\.\s+(?=[A-ZĐÀ-Ỵ])')
DIEM_RE = re.compile(r'^([a-zđ])\)\s+')
REF_RE = re.compile(
    r'Điều\s+(\d+)(?:\s*,\s*(?:khoản|Khoản)\s+(\d+))?'
    r'(?:\s+(?:của|Bộ luật này|Luật này))?'
)
REF_CLAUSE_BEFORE_ARTICLE_RE = re.compile(
    r'(?:khoản|Khoản)\s+(\d+)\s+Điều\s+(\d+)'
)

_ALL_CAPS_TITLE_RE = re.compile(r'^[A-ZĐÀ-Ỵ0-9\s,\.\-]+$')


@dataclass
class LegalNode:
    level: str  # "chuong" | "dieu" | "khoan"
    number: str
    title: str = ""
    text: str = ""
    parent: "LegalNode | None" = None
    children: list = field(default_factory=list)

    def breadcrumb(self) -> dict:
        """Suy ra metadata cấu trúc từ node hiện tại lên gốc - không cần LLM."""
        meta = {}
        node = self
        while node:
            if node.level == "dieu":
                meta["article"] = f"Điều {node.number}"
                meta["article_title"] = node.title
            elif node.level == "khoan":
                meta["clause"] = f"Khoản {node.number}"
            elif node.level == "chuong":
                meta["chapter"] = f"Chương {node.number}: {node.title}".strip(": ")
            node = node.parent
        return meta


class VietnameseLegalParser:
    def __init__(self, law_name: str):
        self.law_name = law_name

    def parse(self, full_text: str) -> list[LegalNode]:
        text = normalize(full_text)
        lines = text.split("\n")

        current_chuong: LegalNode | None = None
        current_dieu: LegalNode | None = None
        current_khoan: LegalNode | None = None
        nodes: list[LegalNode] = []
        buffer: list[str] = []

        def flush_buffer(target: LegalNode | None):
            if target and buffer:
                target.text += "\n".join(buffer).strip() + "\n"
            buffer.clear()

        def take_lookahead_title(i: int) -> tuple[str, int]:
            if i + 1 >= len(lines):
                return "", 0
            next_line = lines[i + 1].strip()
            if not next_line:
                return "", 0
            if CHUONG_RE.match(next_line) or DIEU_RE.match(next_line):
                return "", 0
            if _ALL_CAPS_TITLE_RE.match(next_line):
                return next_line, 1
            return "", 0

        i = 0
        n_lines = len(lines)
        while i < n_lines:
            stripped = lines[i].strip()

            if m := CHUONG_RE.match(stripped):
                flush_buffer(current_khoan or current_dieu)
                title = m.group(2).strip()
                if not title:
                    title, skip = take_lookahead_title(i)
                    i += skip
                current_chuong = LegalNode("chuong", m.group(1), title)
                nodes.append(current_chuong)
                current_dieu = current_khoan = None

            elif m := DIEU_RE.match(stripped):
                flush_buffer(current_khoan or current_dieu)
                current_dieu = LegalNode("dieu", m.group(1), m.group(2).strip(), parent=current_chuong)
                if current_chuong:
                    current_chuong.children.append(current_dieu)
                nodes.append(current_dieu)
                current_khoan = None

            elif current_dieu and (m := KHOAN_RE.match(stripped)):
                flush_buffer(current_khoan or current_dieu)
                current_khoan = LegalNode("khoan", m.group(1), parent=current_dieu)
                current_dieu.children.append(current_khoan)
                nodes.append(current_khoan)
                remainder = stripped[m.end():].strip()
                if remainder:
                    buffer.append(remainder)

            else:
                if stripped:
                    buffer.append(stripped)

            i += 1

        flush_buffer(current_khoan or current_dieu)
        return [n for n in nodes if n.level in ("dieu", "khoan")]

    def parse_articles(self, full_text: str) -> list[LegalNode]:
        """
        Trả về danh sách node cấp Điều (mỗi node có .children là danh sách
        Khoản theo đúng thứ tự gốc trong văn bản). Dùng cho chiến lược
        chunk "gộp nhiều Khoản vào 1 chunk" 
        """
        all_nodes = self.parse(full_text)
        return [n for n in all_nodes if n.level == "dieu"]

    def find_references(self, text: str) -> list[dict]:
        """
        Tìm các tham chiếu "Điều X, khoản Y" xuất hiện trong 1 đoạn text.
        Dùng để cross-check với references do LLM enrichment trích xuất,
        giảm rủi ro LLM bỏ sót hoặc hallucinate tham chiếu.
        """
        refs = []
        for m in REF_RE.finditer(normalize(text)):
            ref = {"article": f"Điều {m.group(1)}"}
            if m.group(2):
                ref["clause"] = f"Khoản {m.group(2)}"
            refs.append(ref)
        seen = {(ref.get("article"), ref.get("clause")) for ref in refs}
        for m in REF_CLAUSE_BEFORE_ARTICLE_RE.finditer(normalize(text)):
            ref = {"article": f"Điều {m.group(2)}", "clause": f"Khoản {m.group(1)}"}
            key = (ref.get("article"), ref.get("clause"))
            if key not in seen:
                refs.append(ref)
                seen.add(key)
        articles_with_clause = {ref["article"] for ref in refs if ref.get("clause")}
        return [
            ref for ref in refs
            if ref.get("clause") or ref.get("article") not in articles_with_clause
        ]
