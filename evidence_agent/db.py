from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AnalyticsDatabase:
    connection: sqlite3.Connection

    @classmethod
    def seeded(cls) -> "AnalyticsDatabase":
        connection = sqlite3.connect(":memory:", check_same_thread=False)
        connection.row_factory = sqlite3.Row
        db = cls(connection)
        db._create_schema()
        db._insert_seed_data()
        return db

    @classmethod
    def connect(cls, path: Path, reset: bool = False) -> "AnalyticsDatabase":
        path.parent.mkdir(parents=True, exist_ok=True)
        if reset and path.exists():
            path.unlink()
        connection = sqlite3.connect(path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        db = cls(connection)
        if reset or not db._has_schema():
            db._create_schema()
            db._insert_seed_data()
        return db

    def detect_customer_name(self, question: str) -> str | None:
        lowered = question.lower()
        rows = self.connection.execute("select name from customers").fetchall()
        for row in rows:
            if row["name"].lower() in lowered:
                return row["name"]
        return None

    def revenue_risk_candidates(self) -> list[dict[str, object]]:
        query = """
        with latest_usage as (
          select
            customer_id,
            round(100.0 * (baseline_events - last_14d_events) / baseline_events, 1) as usage_drop_pct
          from usage_events
        ),
        invoice_summary as (
          select
            customer_id,
            sum(case when status = 'unpaid' then 1 else 0 end) as unpaid_invoices,
            sum(case when status = 'unpaid' then amount_usd else 0 end) as unpaid_amount
          from invoices
          group by customer_id
        ),
        ticket_summary as (
          select
            customer_id,
            sum(case when status = 'open' then 1 else 0 end) as open_tickets,
            sum(case when status = 'open' and severity = 'P1' then 1 else 0 end) as p1_open
          from support_tickets
          group by customer_id
        )
        select
          c.name as customer_name,
          c.segment,
          c.crm_sentiment,
          coalesce(i.unpaid_invoices, 0) as unpaid_invoices,
          coalesce(i.unpaid_amount, 0) as unpaid_amount,
          coalesce(t.open_tickets, 0) as open_tickets,
          coalesce(t.p1_open, 0) as p1_open,
          u.usage_drop_pct,
          (
            coalesce(i.unpaid_invoices, 0) * 25
            + coalesce(t.open_tickets, 0) * 15
            + coalesce(t.p1_open, 0) * 30
            + case when u.usage_drop_pct >= 50 then 25 else 0 end
            + case when s.renewal_days <= 45 then 10 else 0 end
          ) as risk_score
        from customers c
        join subscriptions s on s.customer_id = c.id
        join latest_usage u on u.customer_id = c.id
        left join invoice_summary i on i.customer_id = c.id
        left join ticket_summary t on t.customer_id = c.id
        order by risk_score desc, unpaid_amount desc
        """
        return self._fetch_dicts(query)

    def customer_risk_profile(self, customer_name: str) -> dict[str, object]:
        query = """
        with latest_usage as (
          select
            customer_id,
            round(100.0 * (baseline_events - last_14d_events) / baseline_events, 1) as usage_drop_pct
          from usage_events
        ),
        invoice_summary as (
          select
            customer_id,
            sum(case when status = 'unpaid' then 1 else 0 end) as unpaid_invoices,
            sum(case when status = 'unpaid' then amount_usd else 0 end) as unpaid_amount
          from invoices
          group by customer_id
        ),
        ticket_summary as (
          select
            customer_id,
            sum(case when status = 'open' then 1 else 0 end) as open_tickets,
            sum(case when status = 'open' and severity = 'P1' then 1 else 0 end) as p1_open
          from support_tickets
          group by customer_id
        )
        select
          c.name as customer_name,
          c.segment,
          c.crm_sentiment,
          s.plan,
          s.renewal_days,
          coalesce(i.unpaid_invoices, 0) as unpaid_invoices,
          coalesce(i.unpaid_amount, 0) as unpaid_amount,
          coalesce(t.open_tickets, 0) as open_tickets,
          coalesce(t.p1_open, 0) as p1_open,
          u.usage_drop_pct,
          (
            coalesce(i.unpaid_invoices, 0) * 25
            + coalesce(t.open_tickets, 0) * 15
            + coalesce(t.p1_open, 0) * 30
            + case when u.usage_drop_pct >= 50 then 25 else 0 end
            + case when s.renewal_days <= 45 then 10 else 0 end
          ) as risk_score
        from customers c
        join subscriptions s on s.customer_id = c.id
        join latest_usage u on u.customer_id = c.id
        left join invoice_summary i on i.customer_id = c.id
        left join ticket_summary t on t.customer_id = c.id
        where c.name = ?
        """
        row = self.connection.execute(query, (customer_name,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown customer: {customer_name}")
        return dict(row)

    def plan_health_by_segment(self) -> list[dict[str, object]]:
        query = """
        with latest_usage as (
          select
            customer_id,
            round(100.0 * (baseline_events - last_14d_events) / baseline_events, 1) as usage_drop_pct
          from usage_events
        ),
        invoice_summary as (
          select
            customer_id,
            sum(case when status = 'unpaid' then 1 else 0 end) as unpaid_invoices
          from invoices
          group by customer_id
        ),
        ticket_summary as (
          select
            customer_id,
            sum(case when status = 'open' and severity = 'P1' then 1 else 0 end) as open_p1_tickets
          from support_tickets
          group by customer_id
        )
        select
          c.segment,
          count(distinct c.id) as accounts,
          sum(coalesce(i.unpaid_invoices, 0)) as unpaid_invoices,
          sum(coalesce(t.open_p1_tickets, 0)) as open_p1_tickets,
          round(avg(u.usage_drop_pct), 1) as avg_usage_drop_pct
        from customers c
        join subscriptions s on s.customer_id = c.id
        join latest_usage u on u.customer_id = c.id
        left join invoice_summary i on i.customer_id = c.id
        left join ticket_summary t on t.customer_id = c.id
        group by c.segment
        order by avg_usage_drop_pct desc
        """
        return self._fetch_dicts(query)

    def execute_readonly_sql(self, sql: str) -> list[dict[str, object]]:
        normalized = sql.strip().lower()
        if not normalized.startswith("select") and not normalized.startswith("with"):
            raise ValueError("Only read-only SELECT queries are allowed.")
        blocked = [" insert ", " update ", " delete ", " drop ", " alter ", " pragma "]
        padded = f" {normalized} "
        if any(token in padded for token in blocked):
            raise ValueError("Query contains a blocked SQL operation.")
        return self._fetch_dicts(sql)

    def _fetch_dicts(self, query: str) -> list[dict[str, object]]:
        return [dict(row) for row in self.connection.execute(query).fetchall()]

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            drop table if exists usage_events;
            drop table if exists support_tickets;
            drop table if exists invoices;
            drop table if exists subscriptions;
            drop table if exists customers;

            create table customers (
              id integer primary key,
              name text not null,
              segment text not null,
              crm_sentiment text not null
            );

            create table subscriptions (
              id integer primary key,
              customer_id integer not null,
              plan text not null,
              renewal_days integer not null,
              foreign key(customer_id) references customers(id)
            );

            create table invoices (
              id integer primary key,
              customer_id integer not null,
              amount_usd integer not null,
              status text not null,
              due_days integer not null,
              foreign key(customer_id) references customers(id)
            );

            create table support_tickets (
              id integer primary key,
              customer_id integer not null,
              severity text not null,
              status text not null,
              topic text not null,
              foreign key(customer_id) references customers(id)
            );

            create table usage_events (
              customer_id integer primary key,
              baseline_events integer not null,
              last_14d_events integer not null,
              foreign key(customer_id) references customers(id)
            );
            """
        )

    def _insert_seed_data(self) -> None:
        self.connection.executescript(
            """
            insert into customers values
              (1, 'Acme Retail', 'enterprise', 'healthy'),
              (2, 'Globex Logistics', 'mid-market', 'concerned'),
              (3, 'Northstar Health', 'enterprise', 'neutral'),
              (4, 'BrightPath Studio', 'startup', 'healthy');

            insert into subscriptions values
              (1, 1, 'Enterprise', 28),
              (2, 2, 'Business', 70),
              (3, 3, 'Enterprise', 42),
              (4, 4, 'Starter', 120);

            insert into invoices values
              (1, 1, 42000, 'unpaid', -7),
              (2, 1, 42000, 'paid', 24),
              (3, 2, 12000, 'unpaid', -2),
              (4, 3, 51000, 'paid', 10),
              (5, 4, 900, 'paid', 3);

            insert into support_tickets values
              (1, 1, 'P1', 'open', 'checkout sync outage'),
              (2, 1, 'P2', 'open', 'slow analytics export'),
              (3, 2, 'P3', 'closed', 'seat provisioning'),
              (4, 3, 'P2', 'open', 'SSO configuration'),
              (5, 4, 'P3', 'closed', 'billing address update');

            insert into usage_events values
              (1, 8000, 3000),
              (2, 5000, 2400),
              (3, 9000, 7200),
              (4, 1400, 1300);
            """
        )
        self.connection.commit()

    def _has_schema(self) -> bool:
        row = self.connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'customers'"
        ).fetchone()
        return row is not None
