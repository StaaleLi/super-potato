# Demo Transcript

## Question

Which customers are at revenue risk this week, and what evidence supports it?

## Expected Behavior

The Agent should call SQL because the question asks about customer risk. It should also call retrieval because the user asks for evidence. Finally, it should run an audit because revenue-risk answers can be misleading if they only use invoice status.

## Example Answer

```text
Answer
Acme Retail is the strongest revenue-risk candidate with risk score 120.

Evidence
- SQL: Acme Retail, segment=enterprise, unpaid_invoices=1, open_tickets=2, p1_open=1, usage_drop=62.5%.
- SQL: Globex Logistics, segment=mid-market, unpaid_invoices=1, open_tickets=0, p1_open=0, usage_drop=52.0%.
- Knowledge base [Product Usage Signals]: A usage drop greater than 50 percent in the last 14 days is a risk signal only when paired with unresolved support tickets, unpaid invoices, failed onboarding, or renewal within 45 days.
- Knowledge base [Enterprise Renewal Rules]: Enterprise customers with unresolved P1 tickets must be escalated to the Customer Success Manager before renewal outreach.

Data warnings
- Open P1 ticket changes the allowed next action; escalate before renewal or refund outreach.
- CRM note says the account is healthy, but operational data says risky; manual validation is required.
```
