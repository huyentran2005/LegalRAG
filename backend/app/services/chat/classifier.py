from enum import StrEnum

from app.services.chat.history import _format_memory_for_prompt
from app.services.chat.utils import _llm_text


class QuestionType(StrEnum):
    NORMAL_QA = "Normal QA"
    CONTEXT_DEPENDENT_QA = "Context-dependent QA"
    MULTI_ASPECT_QA = "Multi-aspect QA"


QUESTION_TYPE_VALUES = {item.value.lower(): item for item in QuestionType}
CONTEXT_REFERENCE_PATTERNS = (
    "trên",
    "vừa rồi",
    "câu trên",
    "ý trên",
    "trường hợp trên",
    "trường hợp đó",
    "quy định trên",
    "quy định đó",
    "điều đó",
    "người đó",
    "nội dung trên",
    "như trên",
    "còn trường hợp kia",
)

def _normalize_question_type(text: str) -> QuestionType:
    normalized = " ".join(text.strip().split()).lower()
    normalized = normalized.strip("\"'`.:;- ")

    if normalized in QUESTION_TYPE_VALUES:
        return QUESTION_TYPE_VALUES[normalized]

    for value, question_type in QUESTION_TYPE_VALUES.items():
        if value in normalized:
            return question_type

    return QuestionType.NORMAL_QA


def _looks_context_dependent(current_question: str, memory: list[dict]) -> bool:
    if not memory:
        return False

    normalized = " ".join(current_question.lower().split())
    if not normalized:
        return False

    words = normalized.split()
    has_reference = any(pattern in normalized for pattern in CONTEXT_REFERENCE_PATTERNS)
    if len(words) <= 6 and has_reference:
        return True

    return False


def classify_question_type(llm, memory: list[dict], current_question: str) -> QuestionType:
    if _looks_context_dependent(current_question, memory):
        return QuestionType.CONTEXT_DEPENDENT_QA

    history_block = _format_memory_for_prompt(memory) if memory else "Không có lịch sử hội thoại."
    prompt = f"""
Bạn là bộ phân loại câu hỏi cho hệ thống hỏi đáp pháp luật RAG.
Chỉ trả về đúng một nhãn trong danh sách sau, không giải thích:
- Normal QA
- Context-dependent QA
- Multi-aspect QA

Định nghĩa:
- Normal QA: câu hỏi tự đủ nghĩa, có thể tìm kiếm tài liệu trực tiếp.
- Context-dependent QA: câu hỏi phụ thuộc lịch sử hội thoại để hiểu đúng đối tượng/phạm vi.
- Multi-aspect QA: câu hỏi yêu cầu phân tích nhiều khía cạnh, nhiều nhóm ý, nhiều điều kiện hoặc so sánh nhiều mặt.

Ví dụ Multi-aspect QA:
- Câu hỏi có nhiều đối tượng khác nhau, mỗi đối tượng có điều kiện riêng.
- Câu hỏi có nhiều phương tiện/trường hợp cần trả lời riêng.
- Câu hỏi dạng "trường hợp A ... và trường hợp B ..." hoặc "đồng thời/ngoài ra ...".

[LỊCH SỬ]:
{history_block}

[CÂU HỎI HIỆN TẠI]:
{current_question}

Nhãn:
""".strip()
    try:
        return _normalize_question_type(_llm_text(llm.invoke(prompt)))
    except Exception:
        return QuestionType.NORMAL_QA
