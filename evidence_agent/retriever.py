from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


@dataclass(frozen=True)
class Passage:
    title: str
    text: str
    score: float

    @property
    def preview(self) -> str:
        clean = " ".join(self.text.split())
        return clean[:220] + ("..." if len(clean) > 220 else "")

    def to_dict(self) -> dict[str, object]:
        return {"title": self.title, "score": round(self.score, 3), "preview": self.preview}


class BM25Retriever:
    def __init__(self, passages: list[tuple[str, str]]) -> None:
        self.passages = passages
        self.documents = [self._tokenize(text) for _, text in passages]
        self.avg_doc_len = sum(len(doc) for doc in self.documents) / max(len(self.documents), 1)
        self.document_frequency = self._document_frequency()

    @classmethod
    def from_markdown(cls, path: Path) -> "BM25Retriever":
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Knowledge base file not found: {path}") from exc
        passages: list[tuple[str, str]] = []
        current_title = "Introduction"
        current_lines: list[str] = []

        for line in text.splitlines():
            if line.startswith("## "):
                if current_lines:
                    passages.append((current_title, "\n".join(current_lines).strip()))
                current_title = line[3:].strip()
                current_lines = []
            elif not line.startswith("# "):
                current_lines.append(line)

        if current_lines:
            passages.append((current_title, "\n".join(current_lines).strip()))
        return cls([(title, body) for title, body in passages if body])

    def search(self, query: str, limit: int = 3) -> list[Passage]:
        query_terms = self._tokenize(query)
        scored: list[Passage] = []
        for index, document in enumerate(self.documents):
            score = self._score(query_terms, document)
            if score > 0:
                title, text = self.passages[index]
                scored.append(Passage(title=title, text=text, score=score))
        return sorted(scored, key=lambda p: p.score, reverse=True)[:limit]

    def _score(self, query_terms: list[str], document: list[str]) -> float:
        term_counts = {term: document.count(term) for term in set(document)}
        score = 0.0
        k1 = 1.5
        b = 0.75
        for term in query_terms:
            if term not in term_counts:
                continue
            df = self.document_frequency.get(term, 0)
            idf = math.log(1 + (len(self.documents) - df + 0.5) / (df + 0.5))
            freq = term_counts[term]
            numerator = freq * (k1 + 1)
            denominator = freq + k1 * (1 - b + b * len(document) / self.avg_doc_len)
            score += idf * numerator / denominator
        return score

    def _document_frequency(self) -> dict[str, int]:
        frequency: dict[str, int] = {}
        for document in self.documents:
            for term in set(document):
                frequency[term] = frequency.get(term, 0) + 1
        return frequency

    def _tokenize(self, text: str) -> list[str]:
        return [token.lower() for token in TOKEN_RE.findall(text)]
