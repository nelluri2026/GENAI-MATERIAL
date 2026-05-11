---
doc_id: schema_customers
doc_type: schema
domain: customers
owner: data-platform
status: active
---

# Customers Table

Table name: `demo.customers`

The customers table stores one row per customer.

## Columns

- `customer_id`: primary key. Example: `CUST000001`.
- `customer_name`: customer full name.
- `email`: customer email address.
- `city`: customer city.
- `state`: customer state code.
- `created_at`: timestamp when the customer was created.

## SQL Rules

- Always alias this table as `c`.
- Always qualify columns, for example `c.customer_name`.
- For city, state, name, and email filters, use case-insensitive matching.

