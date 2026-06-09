# Evidence-Aware RAG Agent for B2B Revenue Risk Analysis

一个面向 B2B 客服和收入运营场景的 AI Agent 项目。它不是把问题直接丢给 LLM 的聊天 demo，而是一个可运行的小型业务分析系统：能查知识库、查 SQL、记录工具调用、跑离线评估，并在数据证据互相冲突时主动降级判断。

这个项目适合放在简历或 GitHub 里，用来展示：

- RAG：从产品政策、客服 SOP、合同条款里检索证据片段。
- Agent / tool-use：根据问题自动选择 `knowledge_search`、`sql_query`、`risk_audit` 等工具。
- SQL 多表 JOIN：客户、订阅、工单、账单、产品使用数据一起查询。
- Prompt engineering：把工具结果变成结构化上下文，要求 LLM 不得编造、必须引用证据。
- 数据怀疑意识：如果 SQL、知识库、业务规则之间不一致，Agent 会显式标记。
- 可观测性：每次请求可以写入 JSONL trace，便于复盘工具调用和失败案例。
- 离线评估：内置 eval set，检查工具路由、关键答案和风险警告是否符合预期。

## Why This Project

很多企业聊天机器人失败，不是因为模型不会说话，而是因为它不会区分：

1. 哪些问题应该查文档；
2. 哪些问题必须查数据库；
3. 数据看起来对，但业务含义可能是错的；
4. 缺少证据时应该拒绝下判断。

这个项目把这些问题做成一个可运行的小系统，而不是只写一个 prompt。

## Demo

```bash
python -m evidence_agent "Which customers are at revenue risk this week, and what evidence supports it?"
```

示例输出：

```text
Answer
Acme Retail is the strongest revenue-risk candidate.

Evidence
- SQL: Acme Retail has 1 unpaid invoice, 2 open tickets, and usage dropped by 62.5%.
- Knowledge base: Enterprise renewals with unresolved P1 tickets require escalation before renewal outreach.

Data warnings
- Do not treat invoice status alone as churn evidence. The audit found both payment risk and support risk.
- The answer should be reviewed by a CSM because the P1 ticket changes the allowed next action.
```

## Project Structure

```text
ai-evidence-rag-agent/
  evidence_agent/
    agent.py          # planner + tool orchestration
    auditor.py        # checks contradictions and weak evidence
    db.py             # SQLite schema, seed data, SQL tools
    eval.py           # offline evaluation runner
    llm.py            # optional OpenAI API adapter
    prompts.py        # prompt templates for grounded answers
    retriever.py      # lightweight BM25 retriever
    server.py         # stdlib HTTP service
    trace.py          # JSONL request tracing
  data/
    knowledge_base.md # policies and product docs used by RAG
  docs/
    data-incident.md  # write-up of a real JOIN counting bug
  eval/
    questions.jsonl   # expected tool routes and warning checks
  tests/
    test_agent.py     # standard-library unittest tests
```

## Run Locally

No third-party packages are required.

```bash
cd ai-evidence-rag-agent
python -m evidence_agent "Why is Acme Retail risky?"
python -m evidence_agent "What is the refund policy for enterprise customers?"
python -m evidence_agent "Show plan health by segment"
```

Write request traces:

```bash
python -m evidence_agent "Why is Acme Retail risky?" --trace --log runs/agent_traces.jsonl
```

Run the HTTP service:

```bash
python -m evidence_agent.server --port 8080
```

Then call it:

```bash
curl -X POST http://127.0.0.1:8080/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"Why is Acme Retail risky?\"}"
```

Run the offline eval set:

```bash
python -m evidence_agent.eval
python -m evidence_agent.eval --json
```

Optional LLM synthesis:

```bash
# Windows
set OPENAI_API_KEY=your_api_key_here

# Mac/Linux
export OPENAI_API_KEY=your_api_key_here

python -m evidence_agent "Why is Acme Retail risky?" --use-llm
```

After installing locally with `pip install -e .`, the same commands are also available as:

```bash
evidence-agent "Why is Acme Retail risky?"
evidence-server --port 8080
evidence-eval
```

Without an API key, the project still runs with a deterministic local synthesizer.

## Example Questions

- `Which customers are at revenue risk this week?`
- `Why is Acme Retail risky?`
- `What is the escalation policy for unresolved P1 tickets?`
- `Show plan health by segment`
- `Can we offer a refund to an enterprise customer with an unresolved P1 ticket?`

## What Makes It More Than a Demo

- The database intentionally contains cases where a single metric is misleading.
- The Agent does not blindly trust one source. It cross-checks invoices, product usage, tickets, and policy docs.
- SQL queries use joins across customers, subscriptions, invoices, tickets, and usage events.
- The prompt explicitly forces grounded answers and uncertainty reporting.
- Tests verify routing, retrieval, SQL joins, risk warnings, trace logging, and eval pass rate.
- `docs/data-incident.md` documents a real bug found during development: naive multi-table JOINs duplicated segment counts.

## Evaluation

The eval file `eval/questions.jsonl` contains business questions with expected tool calls, expected warning substrings, and expected answer substrings. This is intentionally simple but important: it turns prompt and Agent behavior into something that can fail in CI instead of being judged by vibes.

Current local result:

```text
eval accuracy: 6/6 = 1.0
```

## Data Incident

During validation, the first segment-health SQL query produced inflated counts because it joined multiple one-to-many tables before aggregation. That made enterprise accounts appear as 5 rows instead of 2.

The fix was to pre-aggregate invoices and tickets by customer, then join those summaries back to customers. The regression test `test_segment_health_does_not_duplicate_joined_rows` protects against the same mistake.

This is the project's main point: the assistant should not only sound good. It should know when its data pipeline can mislead it.

## Limitations

This is a compact portfolio project, not a production deployment. In production I would add:

- vector embeddings instead of lightweight BM25;
- auth and permission control;
- observability for tool calls and prompt traces;
- batch evaluation over real support questions;
- human review workflows for high-risk account actions.
