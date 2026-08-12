import unittest
from app.agent.web_search import WEB_SEARCH_WARNING, _format_web_answer_body
from app.services.chat.citations import (
    _extract_llm_used_citation_indices,
    _format_answer_layout,
    _strip_llm_citation_markers,
)


class CitationFormattingTests(unittest.TestCase):
    def test_extracts_grouped_citation_markers(self):
        chunk_lookup = {1: object(), 2: object(), 3: object()}
        answer = "Ý một [đoạn 1, đoạn 2]. Ý hai [đoạn 2 và 3]."

        self.assertEqual(_extract_llm_used_citation_indices(answer, chunk_lookup), [1, 2, 3]) # type: ignore

    def test_strips_grouped_citation_markers_cleanly(self):
        answer = "Kiểm tra trẻ em khi xuống xe [đoạn 1, đoạn 2]. Không để trẻ trên xe [đoạn 2]."

        self.assertEqual(
            _strip_llm_citation_markers(answer),
            "Kiểm tra trẻ em khi xuống xe. Không để trẻ trên xe.",
        )

    def test_formats_question_headings_without_bullets(self):
        answer = (
            "- Tòa án có thụ lý đơn ly hôn của anh A không?\n"
            "- Không thụ lý vì vợ đang nuôi con dưới 12 tháng tuổi.\n"
            "- Việc tự ý bán xe có giá trị pháp lý không?\n"
            "- Giao dịch vô hiệu nếu không có sự đồng ý của vợ."
        )

        self.assertEqual(
            _format_answer_layout(answer),
            (
                "**Tòa án có thụ lý đơn ly hôn của anh A không?**\n"
                "Không thụ lý vì vợ đang nuôi con dưới 12 tháng tuổi.\n\n"
                "**Việc tự ý bán xe có giá trị pháp lý không?**\n"
                "Giao dịch vô hiệu nếu không có sự đồng ý của vợ."
            ),
        )

    def test_formats_multiple_realistic_legal_answers(self):
        cases = [
            {
                "name": "marriage_property_liability",
                "raw": (
                    "Dựa trên tài liệu:\n"
                    "- Tòa án có thụ lý đơn ly hôn của anh A không?\n"
                    "- Không thụ lý đơn của người chồng khi vợ đang mang thai, sinh con hoặc đang nuôi con dưới 12 tháng tuổi.\n"
                    "- Việc anh A tự ý bán xe có giá trị pháp lý không?\n"
                    "- Giao dịch liên quan đến tài sản chung phải đăng ký mà không có sự thỏa thuận của vợ chồng là vô hiệu.\n"
                    "- Nghĩa vụ bồi thường do tai nạn là nghĩa vụ riêng hay chung?\n"
                    "- Đây là nghĩa vụ riêng nếu phát sinh từ hành vi vi phạm pháp luật của một bên."
                ),
                "expected": [
                    "**Tòa án có thụ lý đơn ly hôn của anh A không?**",
                    "Không thụ lý đơn của người chồng",
                    "**Việc anh A tự ý bán xe có giá trị pháp lý không?**",
                    "là vô hiệu",
                    "**Nghĩa vụ bồi thường do tai nạn là nghĩa vụ riêng hay chung?**",
                    "Đây là nghĩa vụ riêng",
                ],
                "not_expected": ["- Tòa án", "- Việc anh A", "- Nghĩa vụ bồi thường"],
            },
            {
                "name": "traffic_school_pickup",
                "raw": (
                    "- Người lái xe phải kiểm tra trẻ em mầm non, học sinh tiểu học khi xuống xe không?\n"
                    "- Có, người lái xe phải kiểm tra khi trẻ xuống xe.\n"
                    "- Người lái xe có được rời xe khi còn trẻ trên xe không?\n"
                    "- Không, không được để trẻ em mầm non, học sinh tiểu học trên xe khi người quản lý và người lái xe đã rời xe."
                ),
                "expected": [
                    "**Người lái xe phải kiểm tra trẻ em mầm non, học sinh tiểu học khi xuống xe không?**",
                    "Có, người lái xe phải kiểm tra",
                    "**Người lái xe có được rời xe khi còn trẻ trên xe không?**",
                    "Không, không được để trẻ em mầm non",
                ],
                "not_expected": ["- Người lái xe phải", "- Người lái xe có được"],
            },
            {
                "name": "numbered_subquestions",
                "raw": (
                    "1. Tài sản chung phải đăng ký đứng tên một người thì định đoạt thế nào?\n"
                    "Phải có sự thỏa thuận của vợ chồng.\n"
                    "2. Nếu chia tài sản để trốn tránh nghĩa vụ bồi thường thì sao?\n"
                    "Việc chia tài sản đó vô hiệu."
                ),
                "expected": [
                    "1. Tài sản chung phải đăng ký đứng tên một người thì định đoạt thế nào?",
                    "Phải có sự thỏa thuận của vợ chồng.",
                    "2. Nếu chia tài sản để trốn tránh nghĩa vụ bồi thường thì sao?",
                    "Việc chia tài sản đó vô hiệu.",
                ],
                "not_expected": [],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                formatted = _format_answer_layout(case["raw"])
                for expected in case["expected"]:
                    self.assertIn(expected, formatted)
                for not_expected in case["not_expected"]:
                    self.assertNotIn(not_expected, formatted)

    def test_extracts_common_citation_variants(self):
        chunk_lookup = {1: object(), 2: object(), 3: object(), 10: object()}
        cases = [
            ("Căn cứ một [đoạn 1].", [1]),
            ("Căn cứ nhiều [doan 1, doan 2].", [1, 2]),
            ("Căn cứ nối từ [đoạn 2 và 3].", [2, 3]),
            ("Bỏ qua đoạn không tồn tại [đoạn 2, đoạn 99, đoạn 10].", [2, 10]),
        ]

        for answer, expected in cases:
            with self.subTest(answer=answer):
                self.assertEqual(_extract_llm_used_citation_indices(answer, chunk_lookup), expected) # type: ignore

class WebSearchFormattingTests(unittest.TestCase):
    def test_web_answer_keeps_single_warning_and_formats_headings(self):
        answer = (
            "⚠️ Lưu ý: Thông tin tra cứu từ Internet, hãy cẩn trọng.\n\n"
            "⚠️ Lưu ý: Thông tin tra cứu từ Internet mở, hãy cẩn trọng.\n"
            "- Tòa án có thụ lý đơn ly hôn của anh A không?\n"
            "- Không thụ lý theo điều kiện luật định.\n"
            "Nguồn:\n"
            "[1] https://thuvienphapluat.vn/test"
        )

        formatted = _format_web_answer_body(answer, ["https://thuvienphapluat.vn/test"])

        self.assertEqual(formatted.count(WEB_SEARCH_WARNING), 1)
        self.assertIn("**Tòa án có thụ lý đơn ly hôn của anh A không?**", formatted)
        self.assertIn("\n[1] https://thuvienphapluat.vn/test", formatted)
        self.assertNotIn("\n[0] ", formatted)

    def test_web_answer_removes_markdown_links_and_deduplicates_sources(self):
        answer = (
            "Xem quy định tại [Thư viện pháp luật](https://thuvienphapluat.vn/test). "
            "Nguồn:\n"
            "[1] https://thuvienphapluat.vn/test\n"
            "[2] https://example.com/not-allowed"
        )

        formatted = _format_web_answer_body(
            answer,
            ["https://thuvienphapluat.vn/test", "https://thuvienphapluat.vn/test"],
        )

        self.assertEqual(formatted.count("https://thuvienphapluat.vn/test"), 1)
        self.assertNotIn("example.com", formatted)
        self.assertNotIn("](", formatted)

if __name__ == "__main__":
    unittest.main()
