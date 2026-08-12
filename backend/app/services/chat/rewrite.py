import re
from app.services.chat.history import _format_memory_for_prompt
from app.services.chat.utils import _llm_text
from rag.service.answer_parser import  FocusedAnswerParser


def _rewrite_query_with_history(llm, memory: list[dict], current_question: str) -> str:
    prompt = f"""
Viết lại câu hỏi hiện tại thành một câu hỏi độc lập, đầy đủ ngữ cảnh để truy vấn
tài liệu pháp luật. Chỉ trả về đúng câu hỏi đã viết lại, không giải thích.
Giữ nguyên ngôn ngữ tiếng Việt và không thêm thông tin không có trong lịch sử.
Nếu câu hỏi hiện tại chỉ nhắc tới điều/khoản/ý như "Điều 15", "khoản này",
"ý trên", hãy lấy tên luật, chủ đề tranh chấp, đối tượng và phạm vi từ lịch sử
gần nhất để biến thành câu hỏi tự đủ nghĩa. Giữ nguyên số điều/khoản được hỏi.

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
