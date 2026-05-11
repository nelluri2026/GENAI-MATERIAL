---
doc_id: rule_customer_metrics
doc_type: business_rule
domain: customers
owner: sales-operations
status: active
---

# Customer Metrics

## High Value Customer

If the user says high value customer and does not provide a threshold, rank customers by total revenue.

## Active Customer

For this course dataset, an active customer is a customer with at least one order that is not canceled or returned.

## New Customer

New customer means the highest `c.created_at` timestamp unless the user gives a date range.

