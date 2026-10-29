import unittest

from test.rag_evaluator import load_dataset, score_case, summarize


class RagEvaluatorMetricTests(unittest.TestCase):
    def test_scores_good_answer_and_contexts_higher_than_bad_case(self):
        question = "Người chồng có được yêu cầu ly hôn khi vợ đang nuôi con dưới 12 tháng không?"
        expected = "Chồng không có quyền yêu cầu ly hôn khi vợ đang mang thai, sinh con hoặc đang nuôi con dưới 12 tháng tuổi."
        good_answer = "Chồng không được yêu cầu ly hôn khi vợ đang nuôi con dưới 12 tháng tuổi."
        bad_answer = "Người chồng luôn có quyền yêu cầu ly hôn trong mọi trường hợp."
        contexts = [
            {
                "rank": 1,
                "content": "Chồng không có quyền yêu cầu ly hôn khi vợ đang mang thai, sinh con hoặc đang nuôi con dưới 12 tháng tuổi.",
            },
            {
                "rank": 2,
                "content": "Tòa án thụ lý vụ việc dân sự theo quy định chung.",
            },
        ]

        good = score_case(question, expected, good_answer, contexts)
        bad = score_case(question, expected, bad_answer, contexts)

        self.assertGreater(good.answer_relevancy, bad.answer_relevancy)
        self.assertGreater(good.faithfulness, bad.faithfulness)
        self.assertGreater(good.retrieval_recall_at_10, 0.8)
        self.assertGreater(good.context_precision, 0.0)

    def test_summarize_returns_average_metrics(self):
        item = score_case(
            question="Điều kiện A là gì?",
            expected_answer="Điều kiện A là phải có văn bản.",
            generated_answer="Điều kiện A là phải có văn bản.",
            retrieved_contexts=[{"content": "Điều kiện A là phải có văn bản."}],
        )

        report = summarize([item])

        self.assertEqual(report["count"], 1)
        self.assertIn("retrieval_recall_at_10", report["metrics"])
        self.assertIn("answer_relevancy", report["metrics"])

    def test_load_dataset_validates_shape(self):
        with self.assertRaises(FileNotFoundError):
            load_dataset("/tmp/legalrag-missing-eval-file.json")


if __name__ == "__main__":
    unittest.main()
