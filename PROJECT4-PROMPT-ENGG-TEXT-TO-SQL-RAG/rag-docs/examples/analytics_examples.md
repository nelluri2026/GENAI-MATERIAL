---
doc_id: examples_analytics_sql
doc_type: example_sql
domain: ecommerce
owner: data-platform
status: active
---

# Analytics SQL Examples

## Total Revenue By City

Question: What is the total revenue by city?

```sql
SELECT c.city, SUM(o.total_amount) AS revenue
FROM demo.orders o
JOIN demo.customers c ON o.customer_id = c.customer_id
WHERE LOWER(o.status) NOT IN ('canceled', 'returned')
GROUP BY c.city
ORDER BY revenue DESC
LIMIT 50;
```

## Top Customers By Revenue

Question: Who are the top customers by revenue?

```sql
SELECT c.customer_id, c.customer_name, SUM(o.total_amount) AS revenue
FROM demo.orders o
JOIN demo.customers c ON o.customer_id = c.customer_id
WHERE LOWER(o.status) NOT IN ('canceled', 'returned')
GROUP BY c.customer_id, c.customer_name
ORDER BY revenue DESC
LIMIT 50;
```

