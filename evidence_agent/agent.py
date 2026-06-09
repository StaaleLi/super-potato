from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TypeAlias

from .auditor import AuditWarning, RiskAuditor
from .db import AnalyticsDatabase
from .llm import OpenAIChatClient
from .prompts import GROUNDED_ANSWER_PROMPT
from .retriever import BM25Retriever, Passage
from .trace import TraceLogger


SqlPayload: TypeAlias = list[dict[str, object]] | dict[str, object] | None


@dataclass(frozen=True)
class ToolTrace:
    name: str
    reason: str
    output: object


@dataclass(frozen=True)
class AgentResult:
    question: str
    answer: str
    traces: list[ToolTrace]
    warnings: list[AuditWarning]
    passages: list[Passage]

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "answer": self.answer,
            "traces": [
                {"name": trace.name, "reason": trace.reason, "output": trace.output}
                for trace in self.traces
            ],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "passages": [passage.to_dict() for passage in self.passages],
        }


class EvidenceAgent:
    def __init__(
        self,
        database: AnalyticsDatabase | None = None,
        retriever: BM25Retriever | None = None,
        llm: OpenAIChatClient | None = None,
        trace_logger: TraceLogger | None = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parents[1]
        kb_path = base_dir / "data" / "knowledge_base.md"
        self.database = database or AnalyticsDatabase.seeded()
        self.retriever = retriever or BM25Retriever.from_markdown(kb_path)
        self.auditor = RiskAuditor()
        self.llm = llm
        self.trace_logger = trace_logger

    def answer(self, question: str, use_llm: bool = False) -> AgentResult:
        plan = self._plan(question)
        traces: list[ToolTrace] = []
        passages: list[Passage] = []
        sql_payload: SqlPayload = None

        if plan.use_sql:
            sql_payload = self._run_sql_tool(question)
            traces.append(
                ToolTrace(
                    name="sql_query",
                    reason="Question asks about customers, revenue, tickets, invoices, or usage.",
                    output=sql_payload,
                )
            )

        if plan.use_rag:
            retrieval_query = self._augment_retrieval_query(question, sql_payload)
            passages = self.retriever.search(retrieval_query, limit=3)
            traces.append(
                ToolTrace(
                    name="knowledge_search",
                    reason="Question needs policy or support-operation evidence.",
                    output=[p.to_dict() for p in passages],
                )
            )

        warnings = self.auditor.audit(question, sql_payload, passages)
        if warnings:
            traces.append(
                ToolTrace(
                    name="risk_audit",
                    reason="High-stakes business answer needs data-quality checks.",
                    output=[warning.to_dict() for warning in warnings],
                )
            )

        answer = self._synthesize(question, sql_payload, passages, warnings, use_llm)
        result = AgentResult(
            question=question,
            answer=answer,
            traces=traces,
            warnings=warnings,
            passages=passages,
        )
        if self.trace_logger:
            self.trace_logger.write(result.to_dict())
        return result

    def _run_sql_tool(self, question: str) -> SqlPayload:
        normalized = question.lower()
        if "plan health" in normalized or "segment" in normalized:
            return self.database.plan_health_by_segment()

        customer = self.database.detect_customer_name(question)
        if customer:
            return self.database.customer_risk_profile(customer)

        return self.database.revenue_risk_candidates()

    def _augment_retrieval_query(self, question: str, sql_payload: SqlPayload) -> str:
        rows = sql_payload if isinstance(sql_payload, list) else [sql_payload]
        signals: list[str] = []
        for row in rows[:2]:
            if not isinstance(row, dict):
                continue
            if row.get("p1_open", 0) or row.get("open_p1_tickets", 0):
                signals.append("open P1 ticket escalation renewal support severity")
            if row.get("usage_drop_pct", 0) >= 50 or row.get("avg_usage_drop_pct", 0) >= 50:
                signals.append("usage drop product usage signal")
            if row.get("unpaid_invoices", 0):
                signals.append("unpaid invoice churn evidence data quality")
            if row.get("renewal_days", 999) <= 45:
                signals.append("enterprise renewal outreach")
        return " ".join([question, *signals])

    def _synthesize(
        self,
        question: str,
        sql_payload: SqlPayload,
        passages: Iterable[Passage],
        warnings: Iterable[AuditWarning],
        use_llm: bool,
    ) -> str:
        context = self._format_context(sql_payload, passages, warnings)
        if use_llm:
            client = self.llm or OpenAIChatClient.from_environment()
            if client:
                return client.chat(
                    system_prompt=GROUNDED_ANSWER_PROMPT,
                    user_prompt=f"Question:\n{question}\n\nEvidence context:\n{context}",
                )

        return self._local_answer(question, sql_payload, list(passages), list(warnings))

    def _local_answer(
        self,
        question: str,
        sql_payload: SqlPayload,
        passages: list[Passage],
        warnings: list[AuditWarning],
    ) -> str:
        lines = ["Answer"]
        if isinstance(sql_payload, list) and sql_payload:
            top = sql_payload[0]
            if "customer_name" in top:
                lines.append(
                    f"{top['customer_name']} is the strongest revenue-risk candidate "
                    f"with risk score {top['risk_score']}."
                )
            elif "segment" in top:
                lines.append("Plan health varies by segment; the SQL summary is below.")
            else:
                lines.append("The database query returned structured evidence.")
        elif isinstance(sql_payload, dict) and sql_payload:
            lines.append(
                f"{sql_payload['customer_name']} has risk score "
                f"{sql_payload['risk_score']} based on invoices, tickets, and usage."
            )
        elif passages:
            lines.append("The knowledge base contains relevant policy evidence.")
        else:
            lines.append("I do not have enough evidence to answer confidently.")

        lines.append("")
        lines.append("Evidence")
        if sql_payload:
            lines.extend(self._format_sql_evidence(sql_payload))
        for passage in passages[:2]:
            lines.append(f"- Knowledge base [{passage.title}]: {passage.preview}")

        if warnings:
            lines.append("")
            lines.append("Data warnings")
            for warning in warnings:
                lines.append(f"- {warning.message}")

        return "\n".join(lines)

    def _format_sql_evidence(self, payload: SqlPayload) -> list[str]:
        rows = payload if isinstance(payload, list) else [payload]
        lines: list[str] = []
        for row in rows[:4]:
            if not isinstance(row, dict):
                continue
            if "customer_name" in row:
                lines.append(
                    f"- SQL: {row.get('customer_name', 'N/A')}, "
                    f"segment={row.get('segment', 'N/A')}, "
                    f"unpaid_invoices={row.get('unpaid_invoices', 'N/A')}, "
                    f"open_tickets={row.get('open_tickets', 'N/A')}, "
                    f"p1_open={row.get('p1_open', 'N/A')}, "
                    f"usage_drop={row.get('usage_drop_pct', 'N/A')}%."
                )
            elif "segment" in row:
                lines.append(
                    f"- SQL: segment={row.get('segment', 'N/A')}, "
                    f"accounts={row.get('accounts', 'N/A')}, "
                    f"unpaid_invoices={row.get('unpaid_invoices', 'N/A')}, "
                    f"open_p1_tickets={row.get('open_p1_tickets', 'N/A')}, "
                    f"avg_usage_drop={row.get('avg_usage_drop_pct', 'N/A')}%."
                )
        return lines

    def _format_context(
        self,
        sql_payload: SqlPayload,
        passages: Iterable[Passage],
        warnings: Iterable[AuditWarning],
    ) -> str:
        parts = ["SQL_RESULT:", repr(sql_payload), "", "RAG_PASSAGES:"]
        for passage in passages:
            parts.append(f"[{passage.title}] {passage.text}")
        parts.extend(["", "AUDIT_WARNINGS:"])
        for warning in warnings:
            parts.append(f"{warning.severity}: {warning.message}")
        return "\n".join(parts)

    def _plan(self, question: str) -> "_Plan":
        normalized = question.lower()
        # Lightweight deterministic routing keeps this project dependency-free.
        # In production this can be replaced with an intent classifier or an LLM planner.
        sql_terms = [
            "revenue",
            "risk",
            "invoice",
            "usage",
            "segment",
            "plan health",
            "churn",
            "acme",
            "globex",
            "northstar",
        ]
        rag_terms = [
            "policy",
            "refund",
            "rule",
            "why",
            "how",
            "escalation",
            "evidence",
            "support",
            "renewal",
        ]
        return _Plan(
            use_sql=any(term in normalized for term in sql_terms),
            use_rag=any(term in normalized for term in rag_terms)
            or not any(term in normalized for term in sql_terms),
        )


@dataclass(frozen=True)
class _Plan:
    use_sql: bool
    use_rag: bool


def main() -> None:
    parser = argparse.ArgumentParser(description="Evidence-aware RAG agent demo")
    parser.add_argument("question", help="Business question for the agent")
    parser.add_argument("--use-llm", action="store_true", help="Use OpenAI API if OPENAI_API_KEY is set")
    parser.add_argument("--trace", action="store_true", help="Print tool traces after the answer")
    parser.add_argument("--log", help="Optional JSONL path for request traces")
    args = parser.parse_args()

    trace_logger = TraceLogger(Path(args.log)) if args.log else None
    agent = EvidenceAgent(trace_logger=trace_logger)
    result = agent.answer(args.question, use_llm=args.use_llm)
    print(result.answer)

    if args.trace:
        print("\nTool trace")
        for trace in result.traces:
            print(f"- {trace.name}: {trace.reason}")


if __name__ == "__main__":
    main()
