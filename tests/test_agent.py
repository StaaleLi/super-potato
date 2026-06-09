import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from evidence_agent import EvidenceAgent
from evidence_agent.db import AnalyticsDatabase
from evidence_agent.eval import evaluate, load_cases
from evidence_agent.trace import TraceLogger


class EvidenceAgentTest(unittest.TestCase):
    def test_revenue_risk_uses_sql_and_audit(self):
        agent = EvidenceAgent()
        result = agent.answer("Which customers are at revenue risk this week?")

        trace_names = {trace.name for trace in result.traces}
        self.assertIn("sql_query", trace_names)
        self.assertIn("risk_audit", trace_names)
        self.assertIn("Acme Retail", result.answer)

    def test_policy_question_uses_retrieval(self):
        agent = EvidenceAgent()
        result = agent.answer("What is the refund policy for enterprise customers?")

        trace_names = {trace.name for trace in result.traces}
        self.assertIn("knowledge_search", trace_names)
        self.assertNotIn("sql_query", trace_names)
        self.assertIn("Refund Policy", [passage.title for passage in result.passages])

    def test_customer_profile_uses_multi_table_join(self):
        db = AnalyticsDatabase.seeded()
        profile = db.customer_risk_profile("Acme Retail")

        self.assertEqual(profile["unpaid_invoices"], 1)
        self.assertEqual(profile["p1_open"], 1)
        self.assertGreaterEqual(profile["usage_drop_pct"], 50)

    def test_readonly_sql_blocks_mutations(self):
        db = AnalyticsDatabase.seeded()

        with self.assertRaises(ValueError):
            db.execute_readonly_sql("delete from customers")

    def test_segment_health_does_not_duplicate_joined_rows(self):
        db = AnalyticsDatabase.seeded()
        rows = db.plan_health_by_segment()
        enterprise = next(row for row in rows if row["segment"] == "enterprise")

        self.assertEqual(enterprise["accounts"], 2)
        self.assertEqual(enterprise["unpaid_invoices"], 1)
        self.assertEqual(enterprise["open_p1_tickets"], 1)

    def test_trace_logger_writes_jsonl(self):
        with TemporaryDirectory() as temp_dir:
            trace_path = Path(temp_dir) / "trace.jsonl"
            agent = EvidenceAgent(trace_logger=TraceLogger(trace_path))

            agent.answer("Why is Acme Retail risky?")

            content = trace_path.read_text(encoding="utf-8")
            self.assertIn("Acme Retail", content)
            self.assertIn("risk_audit", content)

    def test_eval_suite_passes_current_agent(self):
        base_dir = Path(__file__).resolve().parents[1]
        cases = load_cases(base_dir / "eval" / "questions.jsonl")
        report = evaluate(cases)

        self.assertEqual(report["passed"], report["total"])


if __name__ == "__main__":
    unittest.main()
