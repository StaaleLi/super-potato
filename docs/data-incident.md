# Data Incident: Duplicate Counts From Naive JOINs

## What Happened

The first version of the segment health query joined `customers`, `invoices`, `support_tickets`, and `usage_events` directly, then grouped by customer segment.

That looked reasonable, but it was wrong. Enterprise accounts with multiple invoices and multiple tickets produced multiple joined rows. As a result, account count, unpaid invoice count, and open P1 count were inflated.

## Why It Matters

This is exactly the kind of mistake that makes an AI assistant dangerous in business settings. The language model can sound confident while the upstream SQL result is already wrong.

The problem was not the LLM. The problem was the data shape.

## Fix

I changed the query to aggregate each one-to-many table first:

- invoice summary by customer;
- ticket summary by customer;
- usage summary by customer.

Only then does the query join the summaries back to customers and group by segment.

## Regression Test

The test `test_segment_health_does_not_duplicate_joined_rows` verifies that enterprise accounts are counted as 2, not 5, and that open P1 tickets are counted as 1, not duplicated by invoice rows.

## Lesson

For AI systems that call SQL tools, tool output is not automatically trustworthy. The system needs tests, trace logs, and data-quality checks before the answer reaches a user.
