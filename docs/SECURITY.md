# Security notes

- All ERP pages require an authenticated Django user. Staff-only actions are enforced server-side; read-only accounts cannot submit master-data, sales, purchase, payment, expense or payroll forms.
- Django's CSRF middleware protects POST forms.
- Forms validate required values and numeric bounds server-side.
- The ORM is used for database access; untrusted search values are never concatenated into SQL.
- Financial workflows use atomic database transactions.
- AuditLog records the actor, action, entity, description and request IP for core service actions.
- CSV export escapes values beginning with spreadsheet formula characters (`=`, `+`, `-`, `@`, tab and carriage return).
- `.env`, SQLite databases, virtual environments and generated static files are excluded from version control.

Before any internet-facing deployment: disable DEBUG, set a strong secret key, configure exact hosts and HTTPS cookies, create named least-privilege accounts, use PostgreSQL, review Django's deployment checklist, and arrange encrypted backups and monitoring. The built-in development server is for local testing only.
