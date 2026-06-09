from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .agent import EvidenceAgent
from .trace import TraceLogger


class AgentHandler(BaseHTTPRequestHandler):
    agent: EvidenceAgent
    debug_logs = False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/ask":
            self._send_json({"error": "not found"}, status=404)
            return

        try:
            payload = self._read_json()
            question = payload.get("question")
            if not isinstance(question, str) or not question.strip():
                self._send_json({"error": "question is required"}, status=400)
                return
            result = self.agent.answer(question, use_llm=bool(payload.get("use_llm", False)))
            self._send_json(result.to_dict())
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        if self.debug_logs:
            super().log_message(format, *args)
        return

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size).decode("utf-8")
        return json.loads(body or "{}")

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the evidence agent HTTP service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log", default="runs/agent_traces.jsonl")
    parser.add_argument("--debug", action="store_true", help="Print HTTP request logs")
    args = parser.parse_args()

    AgentHandler.agent = EvidenceAgent(trace_logger=TraceLogger(Path(args.log)))
    AgentHandler.debug_logs = args.debug
    server = ThreadingHTTPServer((args.host, args.port), AgentHandler)
    print(f"serving on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
