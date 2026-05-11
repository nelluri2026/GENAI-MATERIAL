---
doc_id: glossary_sql_terms
doc_type: glossary
domain: ecommerce
owner: data-platform
status: active
---

# SQL Glossary

## Count

Use `COUNT(*)` when the user asks how many rows or records match a condition.

## Average

Use `AVG(o.total_amount)` when the user asks for average order amount.

## Latest

Use descending timestamp order for latest records.

## Most Expensive

Use `ORDER BY o.total_amount DESC`.

