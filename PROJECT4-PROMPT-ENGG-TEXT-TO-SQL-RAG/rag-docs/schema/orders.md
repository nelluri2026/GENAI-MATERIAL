---
doc_id: schema_orders
doc_type: schema
domain: orders
owner: data-platform
status: active
---

# Orders Table

Table name: `demo.orders`

The orders table stores ecommerce orders placed by customers.

## Columns

- `order_id`: primary key. Example: `ORD0000001`.
- `customer_id`: foreign key to `demo.customers.customer_id`.
- `order_date`: timestamp when the order was placed.
- `status`: order lifecycle status.
- `total_amount`: numeric order amount.

## Known Status Values

- `delivered`
- `shipped`
- `processing`
- `canceled`
- `returned`

## SQL Rules

- Always alias this table as `o`.
- Always qualify columns, for example `o.total_amount`.
- Latest order means `ORDER BY o.order_date DESC`.

