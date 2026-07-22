import logging
import re
from dataclasses import dataclass, field
from typing import List

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger("rag.answer_parser")


@dataclass
class SentenceCitation:
    text: str                       # nội dung câu trả lời (không có tag nào cả)
    chunk_index: int | None = None  # số đoạn (1..N) khớp nhất theo embedding, None nếu dưới ngưỡng
    similarity: float = 0.0         # điểm cosine similarity với chunk đó


class FocusedAnswerParser(StrOutputParser):
    """Chỉ làm sạch text thô của LLM, KHÔNG còn yêu cầu/parse tag citation nữa.
    Việc gắn citation được tách ra làm ở bước riêng (post-hoc, xem CitationMatcher),
    để LLM không phải gánh đồng thời "viết chi tiết" + "tự nhớ tag đúng format"."""

    def parse(self, text: str) -> str:
        return self._raw_clean(text)

    @staticmethod
    def _raw_clean(text: str) -> str:
        text = text.strip()
        if "[TRẢ LỜI]:" in text:
            text = text.split("[TRẢ LỜI]:")[-1].strip()
        text = re.sub(r'^\s*[-*]\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _looks_degenerate(text: str, min_chars: int = 4, min_ratio: float = 0.05) -> bool:
        """Phát hiện output bị 'vỡ' — lẫn ký tự ngoài phạm vi tiếng Việt/Latin
        (vd chữ Hán, Nhật, Hàn...), dấu hiệu model bị suy biến khi sinh văn bản.

        Dùng ngưỡng theo TỈ LỆ + SỐ LƯỢNG tối thiểu, thay vì chặn ngay khi có
        1 ký tự lạ — vì đôi khi chunk gốc (do lỗi OCR khi ingest PDF) có thể lẫn
        1-2 ký tự rác, và nếu model chỉ chép lại đúng 1 ký tự đó thì không nên
        coi toàn bộ câu trả lời là suy biến."""
        text = text.strip()
        if not text:
            return False
        foreign_script = re.findall(
            r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', text
        )
        if len(foreign_script) < min_chars:
            return False
        ratio = len(foreign_script) / max(len(text), 1)
        return ratio >= min_ratio

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        candidates = [s.strip() for s in raw_sentences if len(s.strip()) > 5]

        # Lưới an toàn chống lặp câu: một số model nhỏ (hoặc khi generate bị lỗi
        # sampling) có xu hướng lặp lại y hệt/gần giống cùng 1 câu nhiều lần liên tiếp.
        # Loại bỏ câu trùng gần như hoàn toàn với câu đã giữ trước đó.
        deduped: List[str] = []
        for s in candidates:
            normalized = re.sub(r'[^\w\s]', '', s.lower())
            is_duplicate = any(
                normalized == re.sub(r'[^\w\s]', '', kept.lower())
                for kept in deduped
            )
            if not is_duplicate:
                deduped.append(s)

        return deduped[:6]


class OfficeRAG:
    """Model chỉ tập trung viết câu trả lời chi tiết, KHÔNG bị bắt tự gắn citation.
    Prompt được đơn giản hoá tối đa để giảm tải cho model nhỏ (vd Qwen2.5-0.5B)."""

    def __init__(self, llm):
        self.llm = llm
        self.prompt = PromptTemplate.from_template('''
Bạn là trợ lý AI phân tích tài liệu tiếng Việt.

[TÀI LIỆU]:
{context}

[CÂU HỎI]:
{question}

Hãy trả lời câu hỏi dựa HOÀN TOÀN trên tài liệu ở trên.
- Trả lời chi tiết, đầy đủ (3-5 câu), diễn giải rõ ràng, dễ hiểu.
- Không được bịa thêm thông tin ngoài tài liệu.
- Nếu tài liệu không có thông tin liên quan, chỉ cần trả lời: "Không có thông tin nào."
- KHÔNG cần ghi chú nguồn hay số đoạn trong câu trả lời, chỉ cần viết nội dung câu trả lời bình thường.

[TRẢ LỜI]:
''')
        self.answer_parser = FocusedAnswerParser()

    def _call_llm(self, prompt: str) -> str:
        if hasattr(self.llm, "invoke"):
            raw = self.llm.invoke(prompt)
        elif callable(self.llm):
            raw = self.llm(prompt)
        else:
            raise TypeError(f"LLM object {type(self.llm).__name__} is neither callable nor invoke() capable")

        if isinstance(raw, list) and raw:
            first = raw[0]
            if isinstance(first, dict) and "generated_text" in first:
                raw = first["generated_text"]
            else:
                raw = first
        return str(raw)

    def answer(self, context: str, question: str) -> str:
        """Sinh câu trả lời chi tiết THUẦN TÚY, chưa gắn citation.
        Citation được gắn ở bước riêng bên ngoài (xem CitationMatcher trong router)."""
        prompt = self.prompt.format_prompt(context=context, question=question).to_string()
        raw = self._call_llm(prompt)
        logger.info("RAW LLM OUTPUT (question=%r):\n%s", question, raw)
        return self.answer_parser.parse(raw)