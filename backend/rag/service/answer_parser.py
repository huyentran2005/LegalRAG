from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
import re


class FocusedAnswerParser(StrOutputParser):
    def parse(self, text: str) -> str:
        text = text.strip()
        if "[TRẢ LỜI]:" in text:
            answer = text.split("[TRẢ LỜI]:")[-1].strip()
        else:
            answer = text

        answer = re.sub(r'^\s*[-*]\s*', '', answer, flags=re.MULTILINE)
        answer = re.sub(r'\n+', ' ', answer)
        lines = [line.strip() for line in answer.split(". ")
                 if line.strip() and len(line.strip()) > 5]
        return ". ".join(lines[:5]) + ('.' if lines else '')

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        """Tách câu cho tiếng Việt, tránh vỡ ở số thập phân / viết tắt.
        Dùng cho luồng gán citation theo câu (KHÔNG dùng .parse() ở đó,
        vì .parse() cắt còn 5 câu và nối lại, làm mất câu gốc để so khớp)."""
        if not text:
            return []
        text = text.strip()
        if "[TRẢ LỜI]:" in text:
            text = text.split("[TRẢ LỜI]:")[-1].strip()
        text = re.sub(r'^\s*[-*]\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n+', ' ', text).strip()

        # Tách theo . ! ? theo sau bởi khoảng trắng + chữ hoa/đầu câu mới,
        # tránh vỡ ở số thập phân kiểu "3.5 triệu" (không có khoảng trắng
        # + chữ hoa ngay sau dấu chấm trong trường hợp đó).
        parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9])', text)
        return [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]

    @staticmethod
    def _looks_degenerate(text: str) -> bool:
        """Phát hiện output lỗi/suy biến: quá nhiều ký tự lạ ngoài
        Latin/tiếng Việt, hoặc rỗng."""
        if not text or len(text.strip()) < 3:
            return True
        allowed = re.compile(
            r'[a-zA-Z0-9\sÀ-ỹà-ỹ.,!?;:\-\'"()%\[\]/\u0300-\u036f]'
        )
        stripped = allowed.sub('', text)
        if len(stripped) / max(len(text), 1) > 0.15:
            return True
        return False


class OfficeRAG:
    def __init__(self, llm):
        self.llm = llm
        self.prompt = PromptTemplate.from_template("""
        Bạn là trợ lý AI phân tích tài liệu tiếng việt.
        {history_block}
        [TÀI LIỆU]:
        {context}

        [CÂU HỎI]:
        {question}

        Hãy trả lời dựa trên tài liệu. Ghi rõ điều khoản được sử dụng vào câu trả lời. Nếu tài liệu thật sự không có căn cứ nào liên quan, nói rõ "Không có
        thông tin nào." Không dùng câu này khi tài liệu đã có điều/khoản đủ để kết luận.
        Khi câu hỏi yêu cầu đánh giá đúng/sai hoặc phân loại nghĩa vụ/quyền/trách nhiệm,
        phải đối chiếu trực tiếp với điều khoản trong tài liệu. Nếu tài liệu phân biệt
        "nghĩa vụ riêng" và "nghĩa vụ chung", không được tự suy diễn một nghĩa vụ riêng
        thành nghĩa vụ chung chỉ vì có tài sản chung. Nếu tài liệu quy định một giao dịch
        hoặc thỏa thuận "vô hiệu", phải kết luận rõ là vô hiệu, không dùng cách nói mơ hồ
        như "có thể không có hiệu lực".
        Với mỗi ý/câu hỏi con, hãy trả lời theo thứ tự: kết luận trực tiếp trước, sau đó
        nêu căn cứ điều/khoản. Nếu điều luật cho phép kết luận "có", "không", "vô hiệu",
        "nghĩa vụ riêng", hoặc "nghĩa vụ chung", phải dùng đúng kết luận đó; không dùng
        "có thể", "thường", "cần tham khảo thêm", "không thể xác định rõ", "tài liệu
        không cung cấp thông tin cụ thể", hoặc "để có kết luận chính xác" trong cùng ý.
        Chỉ được nói thiếu thông tin khi không có đoạn tài liệu nào chứa căn cứ liên quan
        đến ý đó.
        Trả lời đầy đủ thông tin (3-5 câu chi tiết), không thêm bất kỳ thông tin nào ngoài
        tài liệu. Với mỗi ý dùng thông tin từ tài liệu, ghi citation ngay sau ý đó bằng
        đúng định dạng [đoạn n], trong đó n là số đoạn đã cung cấp. Chỉ cite các đoạn
        thực sự được dùng để trả lời.
        Bố cục câu trả lời phải dễ đọc. Nếu câu hỏi có nhiều ý/câu hỏi con, viết mỗi
        câu hỏi con thành một dòng tiêu đề in đậm dạng **Nội dung câu hỏi?** và KHÔNG
        thêm dấu gạch đầu dòng trước tiêu đề. Viết câu trả lời ngay dưới tiêu đề đó.
        Chỉ dùng gạch đầu dòng cho danh sách nghĩa vụ/điều kiện thật sự, không dùng
        gạch đầu dòng cho cả tiêu đề và câu trả lời. Không dồn nhiều ý đánh số trên
        cùng một dòng.
        [TRẢ LỜI]:
    """)
        self.answer_parser = FocusedAnswerParser()

    @staticmethod
    def _format_history(history: list[dict] | None) -> str:
        if not history:
            return ""
        lines = []
        for turn in history:
            speaker = "Người dùng" if turn.get("role") == "user" else "Trợ lý"
            lines.append(f"{speaker}: {turn.get('content','')}")
        return "[LỊCH SỬ HỘI THOẠI GẦN ĐÂY]:\n" + "\n".join(lines) + "\n"


    def answer(self, context: str, question: str, history: list[dict] | None = None) -> dict:
        """Dùng khi context đã được build sẵn từ bên ngoài (ví dụ endpoint
        tự query DB và đánh số [đoạn i]). Trả về RAW text (chỉ bóc phần
        sau [TRẢ LỜI]:), KHÔNG cắt/nối câu, để giữ nguyên câu gốc cho
        bước gán citation theo câu ở endpoint."""

        history_block = self._format_history(history) # type: ignore
        formatted_prompt = self.prompt.format(context=context, question=question, history_block= history_block)
        raw = self.llm.invoke(formatted_prompt)
        text = self._extract_text(raw)

        if "[TRẢ LỜI]:" in text:
            text = text.split("[TRẢ LỜI]:")[-1].strip()

        prompt_tokens = 0
        completion_tokens = 0
        # Gemini
        if getattr(raw, "usage_metadata", None):
            usage = raw.usage_metadata
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)

        # Ollama
        elif getattr(raw, "response_metadata", None):
            meta = raw.response_metadata or {}
            prompt_tokens = meta.get("prompt_eval_count", 0)
            completion_tokens = meta.get("eval_count", 0)

        total_tokens = prompt_tokens + completion_tokens

        return {
            "token": total_tokens,
            "answer": text.strip(),
        }

    @staticmethod
    def _extract_text(raw) -> str:
        """response.content của langchain_google_genai đôi khi là str,
        đôi khi là list các content block (vd [{"type": "text", "text": "..."}]
        hoặc list các string), tùy phiên bản package. Hàm này chuẩn hóa
        về 1 string duy nhất, ghép các phần text lại với nhau."""
        content = raw.content if hasattr(raw, "content") else raw

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    # dạng phổ biến: {"type": "text", "text": "..."}
                    if "text" in block:
                        parts.append(str(block["text"]))
                    elif block.get("type") == "text" and "content" in block:
                        parts.append(str(block["content"]))
            return "\n".join(parts)

        return str(content)

    def get_chain(self, retriever):
        """Luồng LCEL cho trường hợp CÓ retriever thật (đối tượng hỗ trợ
        `|` / `.invoke()`, ví dụ VectorStoreRetriever của LangChain).
        KHÔNG dùng cho endpoint /chat/ask hiện tại, vì ở đó context được
        build thủ công từ kết quả SQLAlchemy (list các tuple), không phải
        retriever object -> không pipe được bằng `|`."""
        def format_docs(docs):
            formatted = []
            seen = set()
            for doc in docs:
                content = doc.page_content.strip()
                if content not in seen:
                    seen.add(content)
                    formatted.append(f"- {content}")
            return "\n".join(formatted)

        rag_chain = (
            {
                "context": retriever | RunnableLambda(format_docs),
                "question": RunnablePassthrough(),
                "history_block": RunnableLambda(lambda _: ""),
            }
            | self.prompt
            | self.llm
            | self.answer_parser
        )  # type: ignore
        return rag_chain
