# Customer Tool — Data Context (JDWH Data Platform)

Source: docs/reference_readme.md, dbt schema files under
src/02_transform/dbt_core/models/04_product/{customer,finance}, and a live read of
dev_product on 2026-09-28. Row counts are a point-in-time snapshot from that read.

## Overview

CRITICAL: All Customer Tool tables live in the `dev_catalog` catalog, split into a
`dim` schema (dimensions) and a `fact` schema (facts). Use these paths only.

| Table | Full path | Grain | Use it for |
|---|---|---|---|
| dim_customer | dev_catalog.dim.dim_customer | 1 row per customer per channel-validity window (SCD2 on gtm_channel) | Customer counts, channel/tier breakdowns, "who is this client" |
| dim_project | dev_catalog.dim.dim_project | 1 row per project | Project name, type, status, dates, cluster, solution, managers for an invoice line |
| fact_invoice | dev_catalog.fact.fact_invoice | 1 row per invoice line, as billed (no history) | Billing detail, GBP amounts, revenue-type splits |
| fact_channel_bridge | dev_catalog.fact.fact_channel_bridge | 1 row per customer per month (+ wind-down rows) | Why a channel/PE fund's revenue moved (new / churn / expansion) |
| fact_client_bridge | dev_catalog.fact.fact_client_bridge | 1 row per customer per solution per month | Why a client's revenue moved, by service line |

fact_channel_bridge and fact_client_bridge were previously one "Revenue Bridge" table;
they were split so each matches its natural grain.

## Joins

- `customer_sk` = point-in-time join key (customer_nk + gtm_channel + record__valid_from).
  Carried by dim_customer, fact_invoice, fact_channel_bridge → equi-join these directly on it.
- `customer_hk` = entity key (stable identity, no point-in-time awareness).
- fact_client_bridge has ONLY `customer_hk` (no customer_sk, no channel, no cohort columns — by design).
  Join to dim_customer on customer_hk AND `record__is_latest = true`.
- fact_invoice → dim_project on `fact_invoice.project_code = dim_project.project_nk`.
  Use LEFT JOIN: project_code can fall back to a raw source code with no match, and
  14 dim_project rows have NULL project_nk.

| From | To | Join | Declared constraint |
|---|---|---|---|
| fact_invoice | dim_customer | customer_sk | FK fk_invoice_customer |
| fact_channel_bridge | dim_customer | customer_sk | FK fk_channel_bridge_customer |
| fact_client_bridge | dim_customer | customer_hk + record__is_latest = true | None (customer_hk not unique on dim_customer) |
| fact_invoice | dim_project | project_code = project_nk | None (project_nk nullable) |
| fact_channel_bridge | fact_client_bridge | customer_hk (+ ltm_month) | None |

Primary keys: dim_customer(customer_sk), dim_project(project_hk),
fact_invoice(pdt_key), fact_channel_bridge(pdt_key), fact_client_bridge(pdt_key).
Unity Catalog PK/FK are informational only — not enforced.

```sql
-- invoice with point-in-time customer attributes
SELECT i.*, c.customer_name, c.gtm_channel
FROM dev_catalog.fact.fact_invoice i
LEFT JOIN dev_catalog.dim.dim_customer c ON i.customer_sk = c.customer_sk;

-- invoice with project detail
SELECT i.*, p.project_name, p.solution, p.project_status
FROM dev_catalog.fact.fact_invoice i
LEFT JOIN dev_catalog.dim.dim_project p ON p.project_nk = i.project_code;

-- client_bridge with today's customer attributes
SELECT b.*, c.gtm_channel, c.updated_gsb
FROM dev_catalog.fact.fact_client_bridge b
JOIN dev_catalog.dim.dim_customer c
  ON b.customer_hk = c.customer_hk AND c.record__is_latest = true;
```

Query path: start at fact_channel_bridge (or fact_client_bridge for solution detail)
for "why did revenue move", then dim_customer for "who", then fact_invoice for "what
did we bill", then dim_project for "which project".

## Table: dim_customer

dbt model: pdt__customer | dev_catalog.dim.dim_customer | ~436 rows | table, full rebuild
PK: customer_sk

One row per customer as of a point in time. A second row appears only when the sales
channel genuinely changed (SCD2 on gtm_channel). Filter `record__is_latest = true`
for today's picture.

| Column | Type | Meaning |
|---|---|---|
| pdt_key | string | Surrogate key (customer_hk + record__valid_from) |
| customer_hk | string | Entity key, stable across channel change |
| customer_nk | string | Natural key (master customer list code) |
| customer_name | string | Display name |
| customer_sk | string | Point-in-time join key (customer_nk + gtm_channel + record__valid_from). Primary key |
| cluster | string | Current delivery cluster (history in customer_cluster_history) |
| customer_type | string | Corporate / Investment Bank / Other / PE Fund / Portfolio Company / Private company |
| gtm_channel | string | Sales channel, PE fund or bank. Falls back to customer_name for direct clients with no channel (display only, not a real shared channel for cohort/spend-band) |
| gtm_channel_type | string | Investment Bank / PE Fund / Direct clients |
| category | string | Raw descriptive field from master list |
| region | string | — |
| introducer_channel | string | Who originally introduced the relationship, if different |
| introducer_channel_type | string | Investment Bank / PE Fund |
| business_model | string | Customer's industry classification |
| vertical | string | Paired with business_model |
| fund_potential | string | Low / Medium / High |
| depth_of_relationship | string | New / Emerging / Good / Excellent |
| updated_gsb | string | Account tier: Gold / Silver / Bronze / New / Strategic Investment |
| customer_join_date | date | On-file join date; anchor for all cohort calculations |
| jin_client_code | string | Code in Jin (delivery/project system). NULL for ~5 unmatched customer_codes |
| is_active_jin_client | boolean | Active flag from Jin; NULL where jin_client_code is NULL |
| city, state, zipcode, website, customer_linkedin_page | string | Descriptive |
| client_fy_cohort | string | Fiscal year (Sep–Aug) of customer_join_date, e.g. "FY2022-2023" |
| channel_fy_cohort | string | FY of the earliest join date across every customer ever on that channel (incl. transferred away) |
| client_spend_band | string | All-time cumulative revenue: <200k / 200k-500k / 500k-800k / 800k+ |
| channel_spend_band | string | All-time cumulative across channel: <500k / 500k-1M / 1M+. Blank if no channel |
| record__valid_from, record__valid_to, record__is_latest | timestamp, timestamp, boolean | SCD2 window; valid_to NULL for current |

Notes:
- Client cohort = FY of on-file join date (old "infer from earliest invoice" logic retired).
- Spend bands are lifetime cumulative, recomputed every refresh.
- ~11 customer codes have invoiced revenue (~£1.38M combined) with no master record — kept, descriptive fields limited/blank.
- Some customers (e.g. Cinven) have active projects but zero invoices — revenue correctly reads zero.

## Table: dim_project

dev_catalog.dim.dim_project | PK: project_hk

One row per project. Describes what a fact_invoice line was billed against.

| Column | Meaning |
|---|---|
| pdt_key | Surrogate key, unique per row |
| project_hk | Project entity key (hash). Primary key; use for identity |
| project_nk | Source project code; matches fact_invoice.project_code. NULLABLE — 14 rows have no natural key, so no UNIQUE/FK on it |
| project_name | Project display name |
| project_type | Project classification from source system |
| project_start_date | Project start date |
| project_end_date | Planned/actual end date |
| project_extension_date | Revised end date where extended beyond project_end_date |
| project_status | Current lifecycle status |
| customer_code | Customer the project belongs to; same code domain as fact_invoice.customer_code |
| cluster_hk, cluster_name | Delivery cluster key and name |
| solution | Service line (e.g. Core Reporting, Managed Services). Drives fact_invoice.revenue_type = Recurring when Managed Services |
| is_billable | Whether the project is billable |
| manager_hk, manager_name | Project manager |
| engagement_manager_hk, engagement_manager_name | Engagement manager |
| meta__source_system, meta__source_table, meta__loaded_at | Load metadata |

Notes:
- 14 rows with NULL project_nk will never match any invoice line.
- dim_project.solution is related to fact_client_bridge.solution, but the bridge derives its own — don't assume they match per customer-month.

## Table: fact_invoice

dbt model: pdt__invoice | dev_catalog.fact.fact_invoice | ~5,327 rows | table, current-state only
PK: pdt_key | FK: customer_sk → dim_customer.customer_sk

One row per invoice line as billed. No history tracking.

| Column | Type | Meaning |
|---|---|---|
| pdt_key | string | Surrogate key (invoice_tracker_hk) |
| invoice_tracker_hk, invoice_tracker_nk | string | Entity + natural key |
| project_code | string | Project billed against; matches dim_project.project_nk. Falls back to raw source code if unresolved |
| customer_code | string | Customer the invoice belongs to |
| customer_sk | string | Point-in-time key resolved on invoice_date. NULL if no matching channel window |
| currency_code, currency_name | string | Original billing currency |
| currency_rate_date | date | FX rate date used (point-in-time as of invoice_date) |
| rate_to_base, rate_from_base | decimal | FX rates; rate_from_base used for all *_gbp columns |
| invoice_month | date | Period the work relates to. ALL revenue reporting uses this, not invoice_date |
| invoice_date | date | Literal billing date |
| invoice_amount, sub_total, vat, vat_amount, total_invoice_amount | decimal | Original currency |
| invoice_amount_gbp, sub_total_gbp, vat_amount_gbp, total_invoice_amount_gbp | decimal | Historical FX rate. DEFAULT for new analysis |
| sub_total_gbp_fixed | decimal | Flat legacy rate (EUR/1.2, USD/1.3); Sep 2023–Aug 2024 deliberately unconverted raw. ONLY for reconciling to old Excel reports / Bridge tables |
| delivery_model | string | From source |
| cluster | string | Delivery cluster as of invoice_month (point-in-time) |
| revenue_type | string | Recurring / New / Repeating |
| client_spend_band, channel_spend_band | string | Same buckets as dim_customer, but on trailing-12-month window as of invoice_month |

revenue_type:
- Recurring — project service line is Managed Services (decided purely by service line).
- New — billed within first 12 months of BOTH the client's and the client's channel's relationship. A new portco under an established PE fund is Repeating, not New.
- Repeating — everything else.

## Table: fact_channel_bridge

dbt model: pdt__channel_bridge | dev_catalog.fact.fact_channel_bridge | ~19,891 rows | full rebuild every run
PK: pdt_key | FK: customer_sk → dim_customer.customer_sk
Validated dollar-for-dollar against the business's Excel Bridge report.

One row per customer per month, independent of service line. Plus wind-down rows
(`is_channel_history_row = true`): for up to 12 months after a customer transfers out
of a channel, their residual contribution to the old channel appears separately so the
channel total winds down to zero.

| Column | Type | Meaning |
|---|---|---|
| pdt_key | string | Surrogate key |
| customer_hk, customer_nk, customer_sk | string | Entity, natural, point-in-time keys |
| portco | string | Customer display name |
| channel | string | Channel as of ltm_month (label, not partition key; changes on transfer) |
| ltm_month | date | Last month of trailing-12-month window |
| prior_year_ltm_month | date | Same window one year earlier |
| ltm_revenue | decimal | Customer's contribution to this channel over trailing 12 months (per-invoice-month attribution) |
| prior_year_ltm_revenue | decimal | Same, one year earlier |
| yoy_movement | decimal | ltm_revenue − prior_year_ltm_revenue |
| revenue_bucket | string | Movement classification (see below) |
| client_spend_band | string | Customer's full LTM total across all channels. NULL on wind-down rows |
| channel_spend_band | string | Channel-wide LTM total |
| client_cohort, channel_cohort | string | Plain-year cohort |
| client_fy_cohort, channel_fy_cohort | string | "FY2022-23" (2-digit) format — dim_customer uses "FY2022-2023" |
| is_channel_history_row | boolean | true = wind-down row. Filter false for one-row-per-customer; keep both for channel SUM(ltm_revenue) to reconcile |

revenue_bucket values:
| Value | Meaning |
|---|---|
| Channel New | Relationship began within the channel's own first 12 months |
| Channel Cross-Sell | New relationship, channel already past its first 12 months |
| Channel Transfer Netsell | Netsell where the channel label changed between the two periods |
| Channel Netsell | Ongoing relationship, revenue moved, active in both periods |
| Client Churn | Client's revenue stopped; channel may still be active |
| Channel Churn | Entire channel permanently dark |

Vista Equity Partners and Motive Partners are never treated as channels for churn —
always Client Churn, never Channel Churn (hardcoded business decision).

## Table: fact_client_bridge

dbt model: pdt__client_bridge | dev_catalog.fact.fact_client_bridge | ~21,461 rows | full rebuild every run
PK: pdt_key | No FK (joins on customer_hk only)
LESS VALIDATED than fact_channel_bridge — first pass, not signed off. Flag before using
for board-level or external reporting.

One row per customer per solution (service line) per month; each solution has its own
lifecycle.

| Column | Type | Meaning |
|---|---|---|
| pdt_key | string | Surrogate key (customer_hk + solution + ltm_month) |
| customer_hk | string | Entity key — only join key on this table |
| customer_nk | string | Natural key |
| portco | string | Customer display name |
| solution | string | Effective service line (e.g. Core Reporting, Managed Services) |
| ltm_month, prior_year_ltm_month | date | LTM window and year-ago point |
| client_ltm_revenue, client_prior_year_ltm_revenue | decimal | Revenue for customer+solution per window |
| client_bucket | string | Movement classification (see below) |
| client_spend_band | string | Customer's LTM total across all solutions (repeated on each solution row) |

client_bucket values:
| Value | Meaning |
|---|---|
| New Client | Solution started within the client's own first 12 months |
| Solution Cross-Sell | Solution started after the client's first 12 months |
| Solution Netsell | Ongoing service expanded or contracted |
| Solution Churn | This service line stopped; client active via another |
| Client Churn | Entire client relationship stopped |

## Shared concepts

- LTM revenue: every monthly figure on both bridges is a trailing-12-month total, not single-month invoicing. YoY = LTM vs same LTM one year earlier. Never SUM across months.
- Reactivation is never New on either bridge — stop then restart = Netsell.
- Data starts ~September 2022. Bridges trust on-file join date when it predates loaded invoices (~50 of ~384 current customers, join dates back to 2017). If part of the first-12-months window is visible, that part still gets New treatment.

## Known ambiguities

1. Use dev_catalog (dim / fact schemas) for all Customer Tool tables.
2. ~11 customer codes with billed revenue (~£1.38M) and no master record — fact_invoice.customer_sk is NULL for these; always LEFT JOIN.
3. 14 dim_project rows have NULL project_nk; fact_invoice.project_code may not resolve — always LEFT JOIN.
4. Zero-revenue customers exist by design.
5. Two GBP conversions: *_gbp (historical) vs sub_total_gbp_fixed (legacy). Wrong one vs old Excel looks like a discrepancy but isn't.
6. invoice_month can differ from invoice_date by a month or more; reporting uses invoice_month.
7. Vista Equity Partners and Motive Partners hardcoded churn exceptions.
8. fact_client_bridge less validated than fact_channel_bridge.
9. Cohort trend/history reporting retired; only per-row cohort year remains, only on fact_channel_bridge.
10. Cohort format: dim_customer "FY2022-2023" vs fact_channel_bridge "FY2022-23".
11. A new relationship's channel relabel is delayed to month 13 on fact_channel_bridge.
12. Customers with no channel appear on both bridges as a "channel of one" with no Channel Churn/Cross-Sell classification.
13. Always de-dup dim_customer (record__is_latest = true) on a customer_hk join, otherwise multi-version customers fan out fact rows.
14. PK/FK constraints are informational only in Unity Catalog — not enforced.

## Glossary

- Cohort: fiscal year a customer's/channel's relationship began (on-file join date).
- Channel: sales channel, PE fund or investment bank a customer is attributed to.
- Solution: service line a client buys (e.g. Core Reporting, Managed Services).
- LTM revenue: sum of the last 12 calendar months of revenue.
- Churn: revenue stopping permanently, not a gap between invoices.
- Netsell: ongoing relationship whose revenue moved up or down.
- Cross-sell: new service/client added after the channel's/client's first 12 months.
- Left-censoring: relationship started before the data does — why join dates are trusted over first-invoice dates.
- customer_hk / customer_sk: entity key vs point-in-time join key.
- project_hk / project_nk: project entity key vs source project code.
