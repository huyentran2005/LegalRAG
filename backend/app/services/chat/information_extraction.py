import json
import re

from app.services.chat.utils import _llm_text
from rag.service.answer_parser import FocusedAnswerParser


def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    return re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE).strip()


def parse_json_response(text: str) -> dict | list | None:
    cleaned = _clean_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None


def _normalize_aspect(item) -> dict | None:
    if isinstance(item, str):
        question = re.sub(r"\s+", " ", item).strip("\"'` ")
        aspect = {
            "name": question[:80],
            "question": question,
            "entities": [],
            "constraints": [],
            "evidence_need": "",
        }
    elif isinstance(item, dict):
        question = str(item.get("question") or item.get("subquery") or item.get("name") or "").strip()
        aspect = {
            "name": str(item.get("name") or question[:80]).strip(),
            "question": question,
            "entities": item.get("entities") if isinstance(item.get("entities"), list) else [],
            "constraints": item.get("constraints") if isinstance(item.get("constraints"), list) else [],
            "evidence_need": str(item.get("evidence_need") or item.get("required_evidence") or "").strip(),
        }
    else:
        return None

    if not aspect["question"] or FocusedAnswerParser._looks_degenerate(aspect["question"]):
        return None
    return aspect


def _fallback_structured_query(question: str) -> dict:
    return {
        "normalized_question": question,
        "expanded_queries": [question],
        "intent": "",
        "vehicle_type": "",
        "entities": [],
        "constraints": [],
        "aspects": [
            {
                "name": question[:80],
                "question": question,
                "entities": [],
                "constraints": [],
                "evidence_need": "",
            }
        ],
    }


def extract_structured_query(llm, question: str, max_aspects: int = 1) -> dict:
    prompt = f"""
Bạn là bộ Information Extraction cho truy vấn pháp luật.
Trích xuất truy vấn thành dữ liệu có cấu trúc để retrieval.

Yêu cầu:
- normalized_question: câu hỏi đã chuẩn hóa, tự đủ nghĩa để truy vấn.
- Giữ lại các cụm từ khóa quan trọng trong câu hỏi gốc; không thay bằng diễn đạt quá chung.
- Nếu câu hỏi nhắc tới trách nhiệm/chủ thể/hành vi, normalized_question phải giữ các từ đó.
- entities: chủ thể, đối tượng, văn bản, điều/khoản được nhắc tới.
- constraints: điều kiện, thời gian, phạm vi, trường hợp áp dụng.
- expanded_queries: 2-5 câu truy vấn ngắn, mỗi câu tập trung vào một ý cần retrieval.
- Mỗi expanded_query phải giữ nguyên phạm vi văn bản/pháp luật nếu câu hỏi đã nêu.
- Nếu câu hỏi dùng "Luật" nhưng không nêu lại đầy đủ tên luật trong từng ý, retrieval_query/aspect vẫn phải giữ các điều kiện phân biệt từng trường hợp, không gom nhiều trường hợp vào một truy vấn.
- Không biến một cụm mơ hồ thành truy vấn độc lập làm lệch miền. Ví dụ "thành viên khác trong gia đình" trong câu hỏi về Luật Trật tự, an toàn giao thông đường bộ phải được truy vấn kèm phạm vi luật giao thông, không truy vấn như Luật Hôn nhân và Gia đình.
- Nếu câu hỏi có "ngoài ra", "đồng thời", "và" để hỏi thêm nghĩa vụ/trách nhiệm khác, phải tạo expanded_query/aspect riêng cho từng ý.
- Ví dụ câu hỏi vừa hỏi quy tắc chở trẻ em dưới 10 tuổi dưới 1,35 mét trên ô tô, vừa hỏi trách nhiệm thành viên khác trong gia đình theo Luật Trật tự, an toàn giao thông đường bộ, thì tạo ít nhất 2 expanded_queries tương ứng hai ý đó.
- intent: ý định chính, ví dụ penalty, procedure, definition, comparison, obligation.
- vehicle_type: loại phương tiện nếu có, ví dụ ô tô, xe máy, xe tải, xe khách.
- aspects: tối đa {max_aspects} khía cạnh cần tìm bằng chứng. Với Normal QA chỉ cần 1 aspect.

Ví dụ:
[CÂU HỎI]
Khi chở trẻ em dưới 10 tuổi và cao dưới 1,35 mét trên xe ô tô, người lái xe phải tuân thủ quy tắc an toàn nào? Ngoài ra, Luật Trật tự, an toàn giao thông đường bộ quy định trách nhiệm của thành viên khác trong gia đình như thế nào?

[JSON]
{{
  "normalized_question": "Quy tắc an toàn khi chở trẻ em dưới 10 tuổi, cao dưới 1,35 mét trên ô tô và trách nhiệm thành viên gia đình theo Luật Trật tự, an toàn giao thông đường bộ",
  "expanded_queries": [
    "Khi chở trẻ em dưới 10 tuổi cao dưới 1,35 mét trên ô tô quy tắc an toàn",
    "Luật Trật tự an toàn giao thông đường bộ trách nhiệm thành viên khác trong gia đình chấp hành quy tắc an toàn giao thông"
  ],
  "intent": "obligation",
  "vehicle_type": "ô tô",
  "entities": ["trẻ em", "người lái xe", "thành viên khác trong gia đình", "Luật Trật tự, an toàn giao thông đường bộ"],
  "constraints": ["dưới 10 tuổi", "cao dưới 1,35 mét"],
  "aspects": [
    {{"name":"quy tắc an toàn cho trẻ em trên ô tô","question":"quy tắc an toàn khi chở trẻ em dưới 10 tuổi cao dưới 1,35 mét trên ô tô theo Luật Trật tự an toàn giao thông đường bộ","entities":["trẻ em","người lái xe"],"constraints":["dưới 10 tuổi","cao dưới 1,35 mét","ô tô"],"evidence_need":"quy định về vị trí ngồi và thiết bị an toàn cho trẻ em trên ô tô"}},
    {{"name":"trách nhiệm thành viên gia đình","question":"trách nhiệm của thành viên khác trong gia đình theo Luật Trật tự an toàn giao thông đường bộ","entities":["thành viên khác trong gia đình"],"constraints":[],"evidence_need":"quy định về trách nhiệm hỗ trợ, tuyên truyền, nhắc nhở hoặc chấp hành an toàn giao thông"}}
  ]
}}

[CÂU HỎI]
Khi chở một trẻ em 05 tuổi bằng xe máy và một trẻ em khác 09 tuổi cao 1,30m bằng xe ô tô, Luật quy định những quy tắc an toàn cụ thể nào cho từng trường hợp?

[JSON]
{{
  "normalized_question": "Quy tắc an toàn khi chở trẻ em 05 tuổi bằng xe máy và trẻ em 09 tuổi cao 1,30m bằng xe ô tô",
  "expanded_queries": [
    "quy tắc an toàn khi chở trẻ em 05 tuổi bằng xe máy",
    "quy tắc an toàn khi chở trẻ em 09 tuổi cao 1,30m bằng xe ô tô"
  ],
  "intent": "obligation",
  "vehicle_type": "xe máy, ô tô",
  "entities": ["trẻ em", "người lái xe", "xe máy", "xe ô tô"],
  "constraints": ["05 tuổi", "09 tuổi", "cao 1,30m"],
  "aspects": [
    {{"name":"trẻ 05 tuổi đi xe máy","question":"quy tắc an toàn khi chở trẻ em 05 tuổi bằng xe máy","entities":["trẻ em","xe máy","người lái xe"],"constraints":["05 tuổi"],"evidence_need":"quy định áp dụng khi chở trẻ em bằng xe máy"}},
    {{"name":"trẻ 09 tuổi cao 1,30m đi ô tô","question":"quy tắc an toàn khi chở trẻ em 09 tuổi cao 1,30m bằng xe ô tô","entities":["trẻ em","xe ô tô","người lái xe"],"constraints":["09 tuổi","cao 1,30m"],"evidence_need":"quy định áp dụng khi chở trẻ em dưới 10 tuổi và cao dưới ngưỡng an toàn trên ô tô"}}
  ]
}}

[CÂU HỎI]
Trong thời kỳ hôn nhân, người chồng gây tai nạn giao thông và phải bồi thường thiệt hại cho nạn nhân. Nếu người chồng dùng tài sản riêng của mình để bồi thường nhưng không đủ, tài sản chung của vợ chồng có được dùng để thanh toán nghĩa vụ này không? Nếu hai vợ chồng thỏa thuận chia tài sản chung ngay lúc đó để tránh kê biên tài sản bồi thường thì thỏa thuận này có hiệu lực pháp luật không?

[JSON]
{{
  "normalized_question": "Nghĩa vụ bồi thường thiệt hại do chồng gây tai nạn giao thông trong thời kỳ hôn nhân và hiệu lực thỏa thuận chia tài sản chung để tránh kê biên",
  "expanded_queries": [
    "nghĩa vụ riêng về tài sản của vợ chồng phát sinh từ hành vi vi phạm pháp luật bồi thường thiệt hại",
    "thanh toán nghĩa vụ riêng bằng tài sản riêng và phần tài sản trong khối tài sản chung của vợ chồng",
    "chia tài sản chung trong thời kỳ hôn nhân nhằm trốn tránh nghĩa vụ bồi thường thiệt hại vô hiệu"
  ],
  "intent": "obligation_validity",
  "vehicle_type": "",
  "entities": ["người chồng", "vợ chồng", "tài sản riêng", "tài sản chung", "người thứ ba", "nạn nhân"],
  "constraints": ["trong thời kỳ hôn nhân", "bồi thường thiệt hại", "tài sản riêng không đủ", "chia tài sản để tránh kê biên"],
  "aspects": [
    {{"name":"nguồn thanh toán nghĩa vụ bồi thường","question":"nghĩa vụ bồi thường thiệt hại do một bên vợ chồng gây ra là nghĩa vụ riêng hay nghĩa vụ chung và được thanh toán bằng tài sản nào","entities":["vợ chồng","nghĩa vụ bồi thường thiệt hại","tài sản riêng","tài sản chung"],"constraints":["phát sinh từ hành vi vi phạm pháp luật","tài sản riêng không đủ"],"evidence_need":"quy định phân loại nghĩa vụ riêng, nghĩa vụ chung và nguồn tài sản thanh toán"}},
    {{"name":"hiệu lực chia tài sản để tránh bồi thường","question":"thỏa thuận chia tài sản chung trong thời kỳ hôn nhân nhằm trốn tránh nghĩa vụ bồi thường thiệt hại có hiệu lực pháp luật không","entities":["vợ chồng","thỏa thuận chia tài sản chung","người thứ ba"],"constraints":["nhằm trốn tránh nghĩa vụ bồi thường thiệt hại"],"evidence_need":"quy định về trường hợp chia tài sản chung vô hiệu và không làm thay đổi quyền nghĩa vụ với người thứ ba"}}
  ]
}}

Chỉ trả về JSON dạng:
{{
  "normalized_question": "",
  "expanded_queries": [],
  "intent": "",
  "vehicle_type": "",
  "entities": [],
  "constraints": [],
  "aspects": [
    {{"name":"","question":"","entities":[],"constraints":[],"evidence_need":""}}
  ]
}}

[CÂU HỎI]:
{question}

JSON:
""".strip()
    try:
        data = parse_json_response(_llm_text(llm.invoke(prompt)))
    except Exception:
        data = None

    if not isinstance(data, dict):
        return _fallback_structured_query(question)

    normalized_question = str(data.get("normalized_question") or question).strip() or question
    raw_expanded_queries = data.get("expanded_queries") if isinstance(data.get("expanded_queries"), list) else []
    expanded_queries = []
    seen_queries = set()
    for item in raw_expanded_queries: # type: ignore
        query = re.sub(r"\s+", " ", str(item or "")).strip()
        key = query.lower()
        if query and not FocusedAnswerParser._looks_degenerate(query) and key not in seen_queries:
            expanded_queries.append(query)
            seen_queries.add(key)

    raw_aspects = data.get("aspects") if isinstance(data.get("aspects"), list) else []
    aspects = []
    seen = set()
    for item in raw_aspects: # type: ignore
        aspect = _normalize_aspect(item)
        if not aspect:
            continue
        key = aspect["question"].lower()
        if key not in seen:
            aspects.append(aspect)
            seen.add(key)

    if not aspects:
        aspects = _fallback_structured_query(normalized_question)["aspects"]
    if not expanded_queries:
        expanded_queries = [normalized_question]

    return {
        "normalized_question": normalized_question,
        "expanded_queries": expanded_queries[:5],
        "intent": str(data.get("intent") or "").strip(),
        "vehicle_type": str(data.get("vehicle_type") or "").strip(),
        "entities": data.get("entities") if isinstance(data.get("entities"), list) else [],
        "constraints": data.get("constraints") if isinstance(data.get("constraints"), list) else [],
        "aspects": aspects[:max_aspects],
    }


def build_structured_query_context(structured_query: dict) -> str:
    return "[STRUCTURED QUERY]\n" + json.dumps(structured_query, ensure_ascii=False)
