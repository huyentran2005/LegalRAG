import re
from app.services.chat.history import _format_memory_for_prompt,  _question_matches_reference_rule
from app.services.chat.utils import _llm_text
from rag.service.answer_parser import  FocusedAnswerParser


def _classify_needs_history(llm, memory: list[dict], current_question: str) -> bool:
    if not memory:
        return False
    prompt = f"""
Bạn là bộ phân loại truy vấn. Trả lời duy nhất YES hoặc NO.

Cần dùng lịch sử hội thoại nếu câu hỏi hiện tại phụ thuộc vào nội dung trước đó
để hiểu đúng đối tượng, điều, khoản, chủ thể, hoặc phạm vi. Nếu câu hỏi tự đủ
nghĩa để tìm kiếm tài liệu thì trả lời NO.

[LỊCH SỬ]:
{_format_memory_for_prompt(memory)}

[CÂU HỎI HIỆN TẠI]:
{current_question}

YES/NO:
""".strip()
    try:
        text = _llm_text(llm.invoke(prompt)).upper()
    except Exception:
        return False
    return text.startswith("YES") or "YES" in text[:12]


def _rewrite_query_with_history(llm, memory: list[dict], current_question: str) -> str:
    prompt = f"""
Viết lại câu hỏi hiện tại thành một câu hỏi độc lập, đầy đủ ngữ cảnh để truy vấn
tài liệu pháp luật. Chỉ trả về đúng câu hỏi đã viết lại, không giải thích.
Giữ nguyên ngôn ngữ tiếng Việt và không thêm thông tin không có trong lịch sử.

[LỊCH SỬ]:
{_format_memory_for_prompt(memory)}

[CÂU HỎI HIỆN TẠI]:
{current_question}

[CÂU HỎI ĐỘC LẬP]:
""".strip()
    try:
        rewritten = _llm_text(llm.invoke(prompt))
    except Exception:
        return current_question

    rewritten = re.sub(r"^\s*\[?CÂU HỎI ĐỘC LẬP\]?:\s*", "", rewritten, flags=re.IGNORECASE).strip()
    rewritten = rewritten.strip("\"'` ")
    if not rewritten or FocusedAnswerParser._looks_degenerate(rewritten):
        return current_question
    return rewritten


def _contextualize_query(llm, memory: list[dict], current_question: str) -> tuple[str, bool]:
    """
    Neu co lich su hoi thoai, viet lai cau hoi hien tai thanh 1 cau hoi doc
    lap chua du ngu canh, dung de SEARCH (vector + FTS) - KHONG dung cau
    hoi tho neu no phu thuoc ngu canh truoc (VD "Khoan 2 thi sao?" ->
    "Khoan 2 cua Dieu 40 quy dinh gi?"). Khong anh huong cau hoi goc hien
    thi cho user hay luu DB - chi dung noi bo cho buoc search.
    """
    if not memory:
        return current_question, False

    needs_history = _question_matches_reference_rule(current_question)
    if not needs_history:
        needs_history = _classify_needs_history(llm, memory, current_question)

    if not needs_history:
        return current_question, False

    rewritten = _rewrite_query_with_history(llm, memory, current_question)
    return rewritten, rewritten != current_question