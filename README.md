# ENTERPRISE 360

**An integrated ERP + CRM business operating system built with Django.**

Enterprise 360 brings customer relationships, sales, procurement, inventory, invoices, payments, accounting, banking, HR and payroll into one connected workspace. It is designed as a serious portfolio project with a clean executive dashboard, live database-backed KPIs, interactive charts, documented business workflows and automated tests.

![Enterprise 360](docs/architecture-overview.svg)

## What is included

| Area | Capabilities |
|---|---|
| Executive dashboard | Revenue, expenses, cash, receivables, gross profit, inventory value, monthly trend charts, category mix, invoice status, low-stock watch and activity feed |
| CRM | Customer and supplier records, contact information, customer credit limit, open-balance calculation and edit actions |
| Sales | Create a sales order, validate warehouse stock, issue a customer invoice, reduce inventory and post balanced accounting entries |
| Procurement | Receive a supplier purchase, increase inventory, update weighted-average product cost, create a supplier invoice and post accounting entries |
| Inventory | Product catalogue, warehouse-based stock movements, on-hand quantity, reorder thresholds, stock valuation and product editing |
| Finance | Bank accounts, incoming/outgoing movements, customer receipts, supplier payments, expenses, chart of accounts and double-entry journal |
| People | Employee records, departments, job titles, salary information and edit actions |
| Payroll | Monthly payroll runs and payslips with an explicitly illustrative deduction calculation |
| Business intelligence | 12-month sales/expense trend, sales by category, inventory alerts and CSV exports |
| Governance | Django authentication, admin console and audit log for important business actions |

## Design principles

- **Connected workflows:** sales and purchasing update stock, invoices and the general ledger inside database transactions.
- **Accounting checks:** journal entries are validated for equal debit and credit totals before posting.
- **Decimal money fields:** currency calculations use `Decimal`, not binary floating-point.
- **Safe input handling:** Django forms, CSRF protection, ORM queries and server-side validation are used.
- **Export hygiene:** CSV exports prefix spreadsheet formula-leading values to reduce formula injection risk.
- **Local-first:** SQLite is the default for a quick demo; PostgreSQL is available through Docker Compose.

## Requirements

- Python 3.12 or later. Django 6.1.3 supports Python 3.12–3.15 according to the official Django installation FAQ.
- Linux, macOS or Windows.
- Internet access for the first dependency installation and the externally hosted Chart.js/font assets. Charts degrade gracefully if the chart CDN is unavailable, but typography may use local fallback fonts.

## Quick start on Kali Linux

The project has its own virtual environment because it uses Django, which is separate from the Streamlit environment used by NEURODATA.

### 1. First-time setup (run once)

```bash
cd ~/Downloads/ENTERPRISE-360
chmod +x setup.sh start.sh
./setup.sh
```

`setup.sh` creates `.venv`, installs the project dependencies once, creates a private `.env` with a generated Django secret key if one does not already exist, creates the database schema, and loads demo data.

### 2. Start the application (each time you want to use it)

```bash
cd ~/Downloads/ENTERPRISE-360
./start.sh
```

Open **http://127.0.0.1:8000/** in Firefox.

### Demo login

- Username: `admin`
- Password: the value of `ENTERPRISE_ADMIN_PASSWORD` in your local `.env`; the setup default is `ChangeMe12345!`.

This is a local demo credential. Change it before exposing the application to any other machine. No forced first-login password flow is enabled.

### Manual commands

If you prefer to run the setup yourself:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations erp
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

The manual command list is for first-time setup only. On later runs, activate `.venv` and use `python manage.py runserver 127.0.0.1:8000` or `./start.sh`.

## Demo data

`python manage.py seed_demo` is designed to be re-runnable without duplicating the main sample workflows. It creates:

- Atlas Enterprise Group (MAD currency)
- 6 customers and 4 suppliers
- 8 products and a central warehouse with opening stock
- 6 employee records across departments
- 1 operating bank account with opening balance
- linked purchase and sales orders, sales/purchase invoices and partial customer receipts
- sample rent, utilities and marketing expenses
- a demo payroll run
- opening balance, revenue, cost-of-goods-sold, inventory, payment and expense journal entries

All people, companies, bank accounts, transactions and product records are synthetic demo data.

## Main workflows to try

1. Sign in as `admin`.
2. Open **Overview** and review the figures and charts.
3. Open **Sales orders → Add new**. Select an active customer, product and warehouse. The app checks stock before confirming the order.
4. Confirm that the sale created an invoice, an outbound stock movement and balanced journal entries.
5. Open **Invoices → Record payment** and make a partial or full payment against an invoice.
6. Open **Finance & accounting** to see the bank movement and ledger entries.
7. Open **Purchases → Add new** to receive more stock from a supplier.
8. Add an expense and check the bank balance and general ledger.
9. Open **Business intelligence** or export customer, product, sales and expense data as CSV.

## Tests and quality checks

```bash
source .venv/bin/activate
python manage.py makemigrations erp --check --dry-run
python manage.py check
python manage.py test
```

The test suite covers core service-layer business rules: stock reduction on sales, insufficient-stock rejection without partial writes, stock receipt on purchases, payment balance updates and balanced expense journals.

GitHub Actions runs schema generation, migrations, Django system checks and tests on pushes and pull requests.

## Database options

### SQLite (default)

No database server is needed. The local database is stored at `instance/enterprise360.sqlite3`, which is intentionally excluded from Git.

### PostgreSQL (Docker)

1. Set a strong `POSTGRES_PASSWORD` in `.env`.
2. Ensure Docker Engine and the Compose plugin are installed.
3. Run:

```bash
docker compose up --build
```

The web service is exposed on port `8000`; PostgreSQL data is stored in a named Docker volume.

## Project structure

```text
ENTERPRISE-360/
├── enterprise360/             # Django settings, root URLs, WSGI/ASGI
├── erp/                        # ERP domain models, forms, views and services
│   ├── management/commands/    # Idempotent demo-data command
│   ├── migrations/             # Django migrations (generated on initial setup)
│   ├── static/erp/              # Custom UI styling and interactions
│   ├── templates/erp/           # Dashboard and business module screens
│   ├── admin.py                 # Django admin registrations
│   ├── models.py                # Business entities and relationships
│   ├── services.py              # Atomic business workflows and journal posting
│   ├── views.py                 # Authenticated web views and CSV exports
│   └── tests.py                 # Core workflow tests
├── docs/                        # Architecture and process documentation
├── .github/workflows/           # CI checks
├── setup.sh                     # One-time local setup
├── start.sh                     # Start the local server
├── manage.py
├── requirements.txt
├── Dockerfile
└── compose.yaml
```

## Accounting and compliance notes

This release demonstrates double-entry mechanics with a compact sample chart of accounts. It is **not** a certified accounting package and does not claim compliance with Moroccan tax, payroll, CNSS, labor or invoicing regulations. The payroll deduction in the demo is illustrative only (5%) and must not be used to calculate real employee pay. The default VAT rate in the sale/purchase form is a configurable example, not tax advice. Have a qualified Moroccan accountant validate chart-of-account mapping, VAT rules, invoice numbering, retention and payroll before operational use.

The current release focuses on core connected workflows. It does not yet include bank API integrations, e-invoicing authority integrations, advanced multi-company consolidation, approval chains, warehouse transfers, returns/credit notes or statutory payroll calculations.

## Security before deployment

- Set `DJANGO_DEBUG=0` and a new high-entropy `DJANGO_SECRET_KEY`.
- Set a production `DJANGO_ALLOWED_HOSTS` list.
- Serve only behind HTTPS and set `SESSION_COOKIE_SECURE=1`, `CSRF_COOKIE_SECURE=1` and `SECURE_SSL_REDIRECT=1` when TLS is correctly configured.
- Replace demo credentials; create named user accounts and assign minimum required Django permissions/groups.
- Use PostgreSQL, encrypted backups, log monitoring and a deployment-specific secret manager.
- Run `python manage.py check --deploy` and review every warning before public deployment.

## License

MIT. See [LICENSE](LICENSE).
