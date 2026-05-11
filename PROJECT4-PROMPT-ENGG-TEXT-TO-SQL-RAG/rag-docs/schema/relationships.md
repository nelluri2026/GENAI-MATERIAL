---
doc_id: schema_relationships
doc_type: schema
domain: ecommerce
owner: data-platform
status: active
---

# Table Relationships

The ecommerce schema contains customers and orders.

## Customer To Orders

Relationship:

```sql
o.customer_id = c.customer_id
```

Use this join when a question asks for customer attributes and order attributes together.

Example topics that require a join:

- revenue by city
- orders by customer name
- top customers by spend
- customer email for an order
- order counts by customer state

