---
doc_id: rule_order_status_definitions
doc_type: business_rule
domain: orders
owner: operations
status: active
---

# Order Status Definitions

- `processing`: order is received but not shipped.
- `shipped`: order has left the warehouse.
- `delivered`: order was delivered successfully.
- `canceled`: order was canceled before fulfillment.
- `returned`: order was delivered but returned by the customer.

Canceled and returned orders are normally excluded from revenue calculations.

