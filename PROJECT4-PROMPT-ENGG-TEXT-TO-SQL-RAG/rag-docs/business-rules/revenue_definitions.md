---
doc_id: rule_revenue_definitions
doc_type: business_rule
domain: orders
owner: finance
status: active
---

# Revenue Definitions

Revenue is calculated from `demo.orders.total_amount`.

## Default Revenue Rule

Unless the user explicitly asks otherwise, revenue should exclude orders with these statuses:

- `canceled`
- `returned`

Default revenue filter:

```sql
LOWER(o.status) NOT IN ('canceled', 'returned')
```

## Gross Order Value

If the user asks for gross order value or all order value, include every order status.

## Aggregation

For total revenue, use:

```sql
SUM(o.total_amount)
```

