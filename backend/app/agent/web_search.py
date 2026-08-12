from __future__ import annotations
from typing import Literal
from tavily import TavilyClient
import logging
import os
import re
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

WEB_SEARCH_SYSTEM_PROMPT = """Bạn là chuyên gia tổng hợp thông tin pháp lý từ Internet.
Tổng hợp câu trả lời dựa trên các kết quả web cung cấp.

QUY TẮC BẮT BUỘC:
1. Ghi LUÔN Ở ĐẦU CÂU dòng cảnh báo: "⚠️ Lưu ý: Thông tin tra cứu từ Internet mở, hãy cẩn trọng."
2. Nếu kết quả web không đủ để trả lời, nói dứt khoát: "Xin lỗi, không có thông tin online xác thực." và không kèm trích dẫn lung tung.
3. Trích xuất và liệt kê URLs nguồn ở cuối câu trả lời dưới mục "Nguồn:".
4. Mỗi URL nguồn nằm trên một dòng riêng, dạng "[id] https://...", không dùng Markdown link với id là chỉ số bắt đầu bằng 1 và tăng dần.
5. Chỉ sử dụng thông tin có trong [KẾT QUẢ WEB], không suy diễn hoặc thêm khuyến nghị ngoài nguồn.
6. Trả lời bằng tiếng Việt, ngắn gọn, rõ ràng; nếu có nhiều ý thì dùng gạch đầu dòng."""

WEB_SEARCH_NO_VERIFIED_INFO = "Xin lỗi, không có thông tin online xác thực."
WEB_SEARCH_WARNING = "⚠️ Lưu ý: Thông tin tra cứu từ Internet, hãy cẩn trọng."
URL_PATTERN = re.compile(r"https?://[^\s\])>]+")

VN_LEGAL_DOMAINS: tuple[str,...] = (
    "thuvienphapluat.vn",
    "luatvietnam.vn",
    "vbpl.vn",
    "chinhphu.vn",
    "xaydungchinhsach.chinhphu.vn",
    "baochinhphu.vn"
)

_TRANSIENT_EXC_NAMES: tuple[str,...] = (
    "Timeout",
    "ConnectTimeout",
    "ReadTimeout",
    "ConnectionError",
    "ConnectionResetError",
    "RemoteDisconnected",
    "ProtocolError",
    "ChunkedEncodingError",
)

def _is_transient(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in _TRANSIENT_EXC_NAMES:
        return True
    msg = str(exc).lower()
    return "timeout" in msg or "timed out" in msg or "connection" in msg

class TavilySearchTool:
    def __init__(
            self,
            api_key: str | None = None ,
            max_results: int = 5,
            search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "advanced",
            include_domains: tuple[str,...] | list[str] | None = VN_LEGAL_DOMAINS,
            timeout: float = 120.0,
            max_retries: int = 2,
    ):
        key = api_key or os.getenv("TAVILY_API_KEY")
        if not key:
            raise ValueError(
                "TavilySearchTool requires TAVILY_API_KEY env var or api_key arg."
            )
        self.client = TavilyClient(api_key= key) 
        self.max_results = max_results 
        self.search_depth: Literal["basic", "advanced", "fast", "ultra-fast"]= search_depth 
        self.include_domains = list(include_domains) if include_domains else None 
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))

    def search(
        self,
        query: str,
        max_results: int| None = None,
        include_domains: list[str] | None = None,
    ) -> dict: # type: ignore
        domains = include_domains if include_domains is not None else self.include_domains
        attempts = self.max_retries + 1
        last_exc: BaseException | None = None

        for attempt in range(1, attempts + 1):
            try: 
                return self.client.search(
                    query= query,
                    search_depth= self.search_depth,
                    max_results= max_results or self.max_results,
                    include_domains= domains, # type: ignore
                    timeout= self.timeout,
                )
            except Exception as exc:
                last_exc = exc
                if not _is_transient(exc) or attempt >= attempts:
                    raise
                backoff = float(attempt)
                logger.warning(
                    "Tavily transient error (%s: %s) - retrying %d/%d after %.1fs",
                    type(exc).__name__,
                    exc,
                    attempt,
                    self.max_retries,
                    backoff
                )
                time.sleep(backoff)

        assert last_exc is not None
        raise last_exc


def _extract_search_results(response: dict) -> list[dict[str, str]]:
    rows = response.get("results") or []
    results: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        content = str(row.get("content") or row.get("raw_content") or "").strip()
        title = str(row.get("title") or "").strip()
        if url and (content or title):
            results.append({"title": title, "url": url, "content": content})
    return results


def _is_allowed_domain(url: str, allowed_domains: tuple[str, ...] = VN_LEGAL_DOMAINS) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in allowed_domains
    )


def _filter_allowed_results(results: list[dict[str, str]]) -> list[dict[str, str]]:
    return [result for result in results if _is_allowed_domain(result["url"])]


def _format_search_context(results: list[dict[str, str]]) -> str:
    return "\n\n".join(
        (
            f"[Nguồn {index}]\n"
            f"Tiêu đề: {result['title']}\n"
            f"URL: {result['url']}\n"
            f"Nội dung: {result['content'][:1600]}"
        )
        for index, result in enumerate(results, start=1)
    )


def _extract_text(raw) -> str:
    content = raw.content if hasattr(raw, "content") else raw
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
        return "\n".join(part for part in parts if part)
    return str(content)


def _unique_urls(urls: list[str]) -> list[str]:
    unique = []
    seen = set()
    for url in urls:
        cleaned = url.strip().rstrip(".,;")
        if cleaned and cleaned not in seen:
            unique.append(cleaned)
            seen.add(cleaned)
    return unique


def _strip_markdown_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\2", text)


def _format_bullet_layout(text: str) -> str:
    cleaned = re.sub(r"(?<!^)\s+-\s+", "\n- ", text)
    cleaned = re.sub(r":\s*\n-", ":\n\n-", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    lines = []
    inside_group = False
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            inside_group = False
            continue

        is_bullet = line.startswith("- ")
        bullet_text = line[2:].strip() if is_bullet else line
        is_group_heading = is_bullet and bullet_text.rstrip("* ").endswith(":")
        if is_group_heading:
            lines.append(bullet_text)
        elif is_bullet and inside_group:
            lines.append(f"  - {bullet_text}")
        else:
            lines.append(line)
        inside_group = is_group_heading or (inside_group and is_bullet)

    return "\n".join(lines).strip()


def _format_web_answer_body(answer: str, urls: list[str]) -> str:
    answer = _strip_markdown_links(answer.strip())
    answer = answer.replace(WEB_SEARCH_WARNING, "").strip()
    answer = re.sub(r"^\s*Nguồn:\s*", "", answer, flags=re.IGNORECASE).strip()
    answer = re.split(r"\n?\s*Nguồn:\s*", answer, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    source_urls = _unique_urls([url for url in urls or URL_PATTERN.findall(answer) if _is_allowed_domain(url)])
    for url in source_urls:
        answer = answer.replace(url, "").strip()
    answer = re.sub(r"\s*-\s*$", "", answer).strip()
    answer = re.sub(r"[ \t]+", " ", answer)
    answer = _format_bullet_layout(answer)

    source_lines = "\n".join(f"[{idx}] {url}" for idx, url in enumerate(source_urls))
    sources_block = f"\n\nNguồn:\n{source_lines}" if source_lines else "\n\nNguồn:"
    return f"{WEB_SEARCH_WARNING}\n\n{answer or WEB_SEARCH_NO_VERIFIED_INFO}{sources_block}"


def _ensure_required_web_answer_format(answer: str, urls: list[str]) -> str:
    answer = answer.strip()
    if not answer:
        answer = WEB_SEARCH_NO_VERIFIED_INFO
        return _format_web_answer_body(answer, [])

    return _format_web_answer_body(answer, urls)


def answer_from_web_search(question: str, llm, max_results: int = 5) -> dict:
    search_tool = TavilySearchTool(max_results=max_results)
    response = search_tool.search(question, max_results=max_results)
    results = _filter_allowed_results(_extract_search_results(response))
    urls = [result["url"] for result in results if result.get("url")]

    if not results:
        return {
            "answer": _ensure_required_web_answer_format(WEB_SEARCH_NO_VERIFIED_INFO, []),
            "token": 0,
            "urls": [],
        }

    prompt = (
        f"{WEB_SEARCH_SYSTEM_PROMPT}\n\n"
        f"[CÂU HỎI]\n{question}\n\n"
        f"[KẾT QUẢ WEB]\n{_format_search_context(results)}\n\n"
        "[TRẢ LỜI]"
    )
    raw = llm.invoke(prompt)
    answer = _extract_text(raw)

    prompt_tokens = 0
    completion_tokens = 0
    if getattr(raw, "usage_metadata", None):
        usage = raw.usage_metadata
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
    elif getattr(raw, "response_metadata", None):
        meta = raw.response_metadata or {}
        prompt_tokens = meta.get("prompt_eval_count", 0)
        completion_tokens = meta.get("eval_count", 0)

    return {
        "answer": _ensure_required_web_answer_format(answer, urls),
        "token": prompt_tokens + completion_tokens,
        "urls": urls,
    }
