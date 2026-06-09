from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from .agent import EvidenceAgent


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_tools: set[str]
    expected_warning_substrings: list[str]
    expected_answer_substrings: list[str]


def load_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            cases.append(
                EvalCase(
                    question=raw["question"],
                    expected_tools=set(raw.get("expected_tools", [])),
                    expected_warning_substrings=raw.get("expected_warning_substrings", []),
                    expected_answer_substrings=raw.get("expected_answer_substrings", []),
                )
            )
    return cases


def evaluate(cases: list[EvalCase]) -> dict[str, object]:
    agent = EvidenceAgent()
    rows: list[dict[str, object]] = []
    passed = 0

    for case in cases:
        result = agent.answer(case.question)
        actual_tools = {trace.name for trace in result.traces}
        warning_text = " ".join(w.message for w in result.warnings)
        answer_text = result.answer

        tool_ok = case.expected_tools.issubset(actual_tools)
        warning_ok = all(text in warning_text for text in case.expected_warning_substrings)
        answer_ok = all(text in answer_text for text in case.expected_answer_substrings)
        ok = tool_ok and warning_ok and answer_ok
        passed += int(ok)

        rows.append(
            {
                "question": case.question,
                "ok": ok,
                "actual_tools": sorted(actual_tools),
                "expected_tools": sorted(case.expected_tools),
                "tool_ok": tool_ok,
                "warning_ok": warning_ok,
                "answer_ok": answer_ok,
            }
        )

    return {
        "passed": passed,
        "total": len(cases),
        "accuracy": round(passed / max(len(cases), 1), 3),
        "cases": rows,
    }


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run offline agent evaluation")
    parser.add_argument("--cases", default=str(base_dir / "eval" / "questions.jsonl"))
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    report = evaluate(load_cases(Path(args.cases)))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print(f"eval accuracy: {report['passed']}/{report['total']} = {report['accuracy']}")
    for row in report["cases"]:
        status = "PASS" if row["ok"] else "FAIL"
        print(f"{status} | {row['question']} | tools={','.join(row['actual_tools'])}")


if __name__ == "__main__":
    main()
