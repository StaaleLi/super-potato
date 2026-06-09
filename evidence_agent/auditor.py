from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .retriever import Passage


@dataclass(frozen=True)
class AuditWarning:
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "message": self.message}


class RiskAuditor:
    def audit(
        self,
        question: str,
        sql_payload: object | None,
        passages: Iterable[Passage],
    ) -> list[AuditWarning]:
        warnings: list[AuditWarning] = []
        rows = self._rows(sql_payload)
        passage_text = " ".join(p.text.lower() for p in passages)

        for row in rows:
            if "customer_name" not in row:
                if row.get("open_p1_tickets", 0) > 0:
                    warnings.append(
                        AuditWarning(
                            severity="high",
                            message="Segment summary contains open P1 tickets; drill down before acting.",
                        )
                    )
                continue

            if row.get("unpaid_invoices", 0) > 0 and row.get("open_tickets", 0) == 0:
                warnings.append(
                    AuditWarning(
                        severity="medium",
                        message=(
                            "Invoice status is not enough to infer churn risk; "
                            "support and usage evidence should be checked."
                        ),
                    )
                )

            if row.get("p1_open", 0) > 0:
                warnings.append(
                    AuditWarning(
                        severity="high",
                        message=(
                            "Open P1 ticket changes the allowed next action; "
                            "escalate before renewal or refund outreach."
                        ),
                    )
                )

            if row.get("usage_drop_pct", 0) >= 50 and row.get("open_tickets", 0) == 0:
                warnings.append(
                    AuditWarning(
                        severity="medium",
                        message=(
                            "Large usage drop without an open support ticket may be a false positive; "
                            "validate onboarding or seasonal usage."
                        ),
                    )
                )

            if row.get("crm_sentiment") == "healthy" and row.get("risk_score", 0) >= 60:
                warnings.append(
                    AuditWarning(
                        severity="high",
                        message=(
                            "CRM note says the account is healthy, but operational data says risky; "
                            "manual validation is required."
                        ),
                    )
                )

        if "refund" in question.lower() and "should not be promised" in passage_text:
            warnings.append(
                AuditWarning(
                    severity="high",
                    message="Refund answer touches a restricted policy; do not promise a refund without approval.",
                )
            )

        return self._dedupe(warnings)

    def _rows(self, payload: object | None) -> list[dict[str, object]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []

    def _dedupe(self, warnings: list[AuditWarning]) -> list[AuditWarning]:
        seen: set[tuple[str, str]] = set()
        result: list[AuditWarning] = []
        for warning in warnings:
            key = (warning.severity, warning.message)
            if key not in seen:
                seen.add(key)
                result.append(warning)
        return result
