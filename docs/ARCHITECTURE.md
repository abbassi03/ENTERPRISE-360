# Architecture

## High-level design

```text
Browser
  │ Django templates + responsive CSS + Chart.js
  ▼
Django URL / View layer (authenticated)
  │ Forms + server-side validation
  ▼
ERP service layer (transaction.atomic)
  ├── Sales: validate stock → order/item → stock OUT → invoice → journal
  ├── Purchasing: order/item → stock IN → weighted cost update → supplier bill → journal
  ├── Payments: invoice balance check → payment → bank movement → journal
  ├── Expenses: expense → bank OUT → journal
  └── Payroll: period check → payslips → payroll journal
  ▼
Django ORM
  ├── SQLite for local demo
  └── PostgreSQL for Docker/deployment
```

## Domain areas

- Master data: Company, Department, Employee, Customer, Supplier, Product, Warehouse, BankAccount.
- Operations: SalesOrder, SalesOrderItem, PurchaseOrder, PurchaseOrderItem, StockMovement.
- Finance: Invoice, Payment, Expense, BankTransaction, Account, JournalEntry, JournalLine.
- People: PayrollRun and Payslip.
- Governance: Django authentication and AuditLog.

## Workflow integrity

Business mutations are implemented in `erp/services.py` and wrapped in `transaction.atomic`. An exception rolls back the whole business action. A sale records the customer order, deducts stock, issues a sales invoice, posts revenue/VAT and cost-of-goods-sold journal entries. A purchase receives stock, updates the weighted-average product cost and records the supplier payable. Payments settle invoice balances and update the bank account via a bank transaction and journal entry.

Journal posting validates that total debits equal total credits before creating the entry. The ledger is intentionally append-oriented; do not edit posted journal lines directly in the admin interface for live financial use.

## Data and currency

All monetary values use Django `DecimalField`. The default demonstration currency is MAD. This project is currently single-company and single-currency in its UI, although `Company` and bank records store currency attributes.

## Future extension points

Separate Django apps can be extracted from the domain modules as the system grows (CRM, inventory, sales, procurement, finance, HR). API endpoints, asynchronous tasks, approval workflows and multi-company boundaries should be added as distinct architecture changes with migrations and regression tests.
