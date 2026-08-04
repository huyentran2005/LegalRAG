"""
Chiến lược chunk theo đúng lưu đồ:

for mỗi Điều:
    if Điều <= MAX_TOKEN:
        -> 1 chunk = cả Điều (giữ nguyên vẹn, không vỡ vụn theo Khoản)
    else:
        chia theo Khoản
        for mỗi Khoản:
            nếu Khoản <= MAX_TOKEN:
                -> GỘP nhiều Khoản liên tiếp vào cùng 1 chunk
                   (miễn tổng token <= MAX_TOKEN)
            else:
                chia theo Điểm (a, b, c...)
                nếu 1 Điểm vẫn > MAX_TOKEN:
                    chia theo token (sliding window)
"""

import re
from rag.service.parser import LegalNode

try:
    import tiktoken
    _encoder = tiktoken.get_encoding("cl100k_base")
except ImportError:
    _encoder = None

try:
    from omnichunk import chunk as _omnichunk_chunk
    _HAS_OMNICHUNK = True
except ImportError:
    _HAS_OMNICHUNK = False

_CHARS_PER_TOKEN_VI = 2.8

_DIEM_SPLIT_RE = re.compile(r'\n(?=[a-zđ]\)\s)') # type: ignore

DEFAULT_MAX_TOKENS = 800
DEFAULT_OVERLAP_TOKENS = 100  


# --------------------------------------------------------------------------
# Đếm token
# --------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    if _encoder is not None:
        return len(_encoder.encode(text))
    return int(len(text) / _CHARS_PER_TOKEN_VI)


def estimate_chars(n_tokens: int) -> int:
    return int(n_tokens * _CHARS_PER_TOKEN_VI)


def _tail_tokens(text: str, n_tokens: int) -> str:
    """N token cuối cùng của text - dùng làm phần overlap nối vào chunk kế tiếp."""
    if n_tokens <= 0 or not text:
        return ""
    if _encoder is not None:
        ids = _encoder.encode(text)
        if len(ids) <= n_tokens:
            return text
        return _encoder.decode(ids[-n_tokens:])
    max_chars = estimate_chars(n_tokens)
    return text[-max_chars:]


# --------------------------------------------------------------------------
# Sliding window 
# --------------------------------------------------------------------------

def _sliding_token_windows(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """
    Cắt 1 đoạn text thành các cửa sổ token có overlap chồng lấn.
    """
    if estimate_tokens(text) <= max_tokens:
        return [text]

    if _HAS_OMNICHUNK:
        overlap_ratio = overlap_tokens / max_tokens if max_tokens else 0.0
        try:
            oc_chunks = _omnichunk_chunk(
                "fragment.txt",
                text,
                max_chunk_size=max_tokens,
                size_unit="tokens",
                overlap=overlap_ratio,
            )
            windows = [c.text for c in oc_chunks]
            if windows:
                return windows
        except Exception:
            pass

    step = max(1, max_tokens - overlap_tokens)
    if _encoder is not None:
        ids = _encoder.encode(text)
        windows = []
        i = 0
        while i < len(ids):
            windows.append(_encoder.decode(ids[i:i + max_tokens]))
            if i + max_tokens >= len(ids):
                break
            i += step
        return windows

    max_chars = estimate_chars(max_tokens)
    step_chars = estimate_chars(step)
    windows = []
    i = 0
    while i < len(text):
        windows.append(text[i:i + max_chars])
        if i + max_chars >= len(text):
            break
        i += step_chars
    return windows


# --------------------------------------------------------------------------
# Tiện ích dựng nội dung từ node
# --------------------------------------------------------------------------

def _khoan_content(khoan: LegalNode) -> str:
    """Dựng lại dạng gốc 'N. nội dung...' của 1 Khoản."""
    return f"{khoan.number}. {khoan.text.strip()}"


def _full_article_text(dieu: LegalNode) -> str:
    """
    Ghép toàn bộ nội dung của 1 Điều: phần thân trực tiếp (nếu có, trường
    hợp Điều không chia Khoản) + toàn bộ Khoản con theo đúng thứ tự.
    """
    parts = []
    own_text = dieu.text.strip()
    if own_text:
        parts.append(own_text)
    for khoan in dieu.children:
        parts.append(_khoan_content(khoan))
    return "\n".join(parts)


def _article_header(dieu: LegalNode) -> str:
    title = f". {dieu.title}" if dieu.title else ""
    return f"Điều {dieu.number}{title}"


# --------------------------------------------------------------------------
# Chunk 1 Khoản quá dài (không gộp được với Khoản khác) -> chia theo Điểm,
# overlap giữa các Điểm; nếu 1 Điểm vẫn quá dài -> chia theo token.
# --------------------------------------------------------------------------

def _chunk_oversized_khoan(khoan: LegalNode, dieu_meta: dict, header: str,
                            max_tokens: int, overlap_tokens: int) -> list[dict]:
    text = khoan.text.strip()
    clause_meta = {**dieu_meta, "clauses": [f"Khoản {khoan.number}"]}

    parts = [p.strip() for p in _DIEM_SPLIT_RE.split(text) if p.strip()]

    if len(parts) <= 1:
        # Không có cấu trúc Điểm để bám vào -> chia thẳng theo cửa sổ token
        windows = _sliding_token_windows(text, max_tokens, overlap_tokens)
        return [
            {
                "content": f"{header}, Khoản {khoan.number}\n{w}".strip(),
                "metadata": {**clause_meta, "token_window_index": i},
            }
            for i, w in enumerate(windows)
        ]

    chunks = []
    prev_tail = ""
    for i, p in enumerate(parts):
        content_with_overlap = f"{prev_tail}\n{p}".strip() if prev_tail else p

        if estimate_tokens(content_with_overlap) <= max_tokens:
            chunks.append({
                "content": f"{header}, Khoản {khoan.number}\n{content_with_overlap}".strip(),
                "metadata": {**clause_meta, "point_index": i},
            })
            prev_tail = _tail_tokens(p, overlap_tokens)
        else:
            # 1 Điểm vẫn quá dài dù đã cộng overlap -> chia tiếp theo token
            windows = _sliding_token_windows(p, max_tokens, overlap_tokens)
            for j, w in enumerate(windows):
                chunks.append({
                    "content": f"{header}, Khoản {khoan.number}\n{w}".strip(),
                    "metadata": {**clause_meta, "point_index": i, "token_window_index": j},
                })
            prev_tail = _tail_tokens(p, overlap_tokens)

    return chunks


# --------------------------------------------------------------------------
# Gộp nhiều Khoản liên tiếp vào cùng 1 chunk (greedy bin-packing), overlap
# giữa các nhóm. Khoản nào tự nó đã > max_tokens thì tách riêng, xử lý qua
# _chunk_oversized_khoan thay vì gộp.
# --------------------------------------------------------------------------

def _pack_khoan_greedy(khoan_nodes: list[LegalNode], dieu_meta: dict, header: str,
                        max_tokens: int, overlap_tokens: int) -> list[dict]:
    result: list[dict] = []

    pending_labels: list[str] = []
    pending_texts: list[str] = []
    pending_tokens = 0
    prev_tail = ""  # overlap mang từ group Khoản-gộp liền trước

    def flush_group():
        nonlocal pending_labels, pending_texts, pending_tokens, prev_tail
        if not pending_texts:
            return
        payload = "\n".join(pending_texts)
        text_with_overlap = f"{prev_tail}\n{payload}".strip() if prev_tail else payload
        result.append({
            "content": f"{header}\n{text_with_overlap}".strip(),
            "metadata": {**dieu_meta, "clauses": pending_labels[:]},
        })
        prev_tail = _tail_tokens(payload, overlap_tokens)
        pending_labels, pending_texts, pending_tokens = [], [], 0

    for khoan in khoan_nodes:
        content = _khoan_content(khoan)
        content_tokens = estimate_tokens(content)

        if content_tokens > max_tokens:
            # Bản thân Khoản này đã vượt ngưỡng: chốt nhóm đang gộp dở (nếu
            # có), xử lý Khoản này riêng qua chia Điểm/token, rồi tiếp tục
            # gộp nhóm mới cho các Khoản kế tiếp.
            flush_group()
            oversized_chunks = _chunk_oversized_khoan(
                khoan, dieu_meta, header, max_tokens, overlap_tokens
            )
            result.extend(oversized_chunks)
            prev_tail = ""  # overlap đã xử lý nội bộ trong oversized_chunks
            continue

        if pending_tokens + content_tokens > max_tokens and pending_texts:
            flush_group()

        pending_labels.append(f"Khoản {khoan.number}")
        pending_texts.append(content)
        pending_tokens += content_tokens

    flush_group()
    return result


# --------------------------------------------------------------------------
# Entry point: chunk 1 Điều theo đúng lưu đồ
# --------------------------------------------------------------------------

def chunk_dieu(dieu: LegalNode, law_name: str,
               max_tokens: int = DEFAULT_MAX_TOKENS,
               overlap_tokens: int = DEFAULT_OVERLAP_TOKENS) -> list[dict]:
    meta = dieu.breadcrumb()
    meta["law"] = law_name
    header = _article_header(dieu)
    full_text = _full_article_text(dieu)

    if not full_text:
        return []

    # --- Case 1: cả Điều vừa trong ngưỡng -> 1 chunk duy nhất, không vỡ vụn ---
    if estimate_tokens(full_text) <= max_tokens:
        return [{"content": f"{header}\n{full_text}".strip(), "metadata": meta}]

    # --- Case 2: Điều quá dài -> chia theo Khoản, gộp tối đa, overlap ---
    if dieu.children:
        return _pack_khoan_greedy(dieu.children, meta, header, max_tokens, overlap_tokens)

    # --- Case 3: Điều quá dài nhưng KHÔNG có Khoản con (văn xuôi liền mạch)
    # -> chia thẳng theo cửa sổ token với overlap ---
    windows = _sliding_token_windows(full_text, max_tokens, overlap_tokens)
    return [
        {
            "content": f"{header}\n{w}".strip(),
            "metadata": {**meta, "token_window_index": i},
        }
        for i, w in enumerate(windows)
    ]


def chunk_document(dieu_nodes: list[LegalNode], law_name: str,
                    max_tokens: int = DEFAULT_MAX_TOKENS,
                    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS) -> list[dict]:
    """
    Chunk toàn bộ văn bản. Input là kết quả của
    VietnameseLegalParser.parse_articles() (danh sách node cấp Điều, mỗi
    node có .children là các Khoản theo thứ tự gốc).
    """
    chunks: list[dict] = []
    for dieu in dieu_nodes:
        chunks.extend(chunk_dieu(dieu, law_name=law_name,
                                  max_tokens=max_tokens, overlap_tokens=overlap_tokens))
    return chunks