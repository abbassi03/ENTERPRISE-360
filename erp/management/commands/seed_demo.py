import os
from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from erp.models import (
    BankAccount, Company, Customer, Department, Employee, Expense, Product,
    StockMovement, Supplier, Warehouse, SalesOrder, Invoice, JournalEntry, PayrollRun,
)
from erp.services import create_expense, create_purchase, create_sale, create_payroll_run, record_payment, post_journal

User = get_user_model()

class Command(BaseCommand):
    help = "Create an example company with linked demo customers, products, purchases, sales and finance data."

    @transaction.atomic
    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(username="admin", defaults={
            "email": "admin@enterprise360.local", "is_staff": True, "is_superuser": True,
        })
        if created:
            user.set_password(os.getenv("ENTERPRISE_ADMIN_PASSWORD", "Admin12345!"))
            user.save()
        else:
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])

        Company.objects.get_or_create(name="Atlas Enterprise Group", defaults={
            "legal_name": "Atlas Enterprise Group SARL", "email": "hello@atlas-enterprise.local",
            "phone": "+212 5 22 00 00 00", "address": "Casablanca, Morocco", "currency": "MAD",
        })
        departments = {}
        for name in ["Sales", "Finance", "Operations", "Human Resources", "Procurement"]:
            departments[name], _ = Department.objects.get_or_create(name=name)
        warehouse, _ = Warehouse.objects.get_or_create(code="CAS-01", defaults={"name": "Casablanca Central Warehouse", "location": "Casablanca, Morocco"})
        bank, _ = BankAccount.objects.get_or_create(name="Main Operating Account", defaults={
            "bank_name": "Demo Bank", "account_number_masked": "•••• 4821", "currency": "MAD",
            "opening_balance": Decimal("285000.00"),
        })

        customers_data = [
            ("CUS-1001", "Northstar Retail", "procurement@northstar.local", "Casablanca"),
            ("CUS-1002", "BluePeak Solutions", "finance@bluepeak.local", "Rabat"),
            ("CUS-1003", "Cedar & Co.", "accounts@cedar.local", "Marrakech"),
            ("CUS-1004", "Nova Distribution", "orders@nova.local", "Tangier"),
            ("CUS-1005", "Atlas Hospitality", "admin@atlas-hospitality.local", "Agadir"),
            ("CUS-1006", "Orion Systems", "billing@orion.local", "Fes"),
        ]
        customers = []
        for code, name, email, city in customers_data:
            obj, _ = Customer.objects.get_or_create(customer_code=code, defaults={"name": name, "email": email, "phone": "+212 6 00 00 00 00", "city": city, "credit_limit": Decimal("100000.00")})
            customers.append(obj)

        suppliers_data = [
            ("SUP-2001", "TechSource Maroc", "Casablanca"),
            ("SUP-2002", "OfficeWorks Distribution", "Rabat"),
            ("SUP-2003", "Global Components", "Tangier"),
            ("SUP-2004", "Modern Furniture House", "Marrakech"),
        ]
        suppliers = []
        for code, name, city in suppliers_data:
            obj, _ = Supplier.objects.get_or_create(supplier_code=code, defaults={"name": name, "contact_name": "Account Manager", "email": f"contact@{code.lower()}.local", "phone": "+212 5 20 00 00 00", "city": city})
            suppliers.append(obj)

        product_data = [
            ("PRD-001", "Business Laptop Pro 14", "ELECTRONICS", "7200.00", "9490.00", "10"),
            ("PRD-002", "Wireless Office Headset", "ELECTRONICS", "420.00", "690.00", "15"),
            ("PRD-003", "4K Conference Display", "ELECTRONICS", "3800.00", "5250.00", "5"),
            ("PRD-004", "Ergonomic Office Chair", "FURNITURE", "950.00", "1490.00", "8"),
            ("PRD-005", "Executive Desk 160cm", "FURNITURE", "1650.00", "2490.00", "4"),
            ("PRD-006", "Laser Printer Network", "OFFICE", "1250.00", "1790.00", "6"),
            ("PRD-007", "USB-C Docking Station", "ELECTRONICS", "560.00", "890.00", "12"),
            ("PRD-008", "Document Scanner A4", "OFFICE", "780.00", "1190.00", "5"),
        ]
        products = []
        for sku, name, category, cost, sale, reorder in product_data:
            obj, _ = Product.objects.get_or_create(sku=sku, defaults={"name": name, "category": category, "cost_price": Decimal(cost), "sale_price": Decimal(sale), "reorder_level": Decimal(reorder), "description": "Demo catalogue item for Enterprise 360."})
            products.append(obj)
            if not obj.stock_movements.exists():
                opening_qty = Decimal("3.00") if sku == "PRD-008" else (Decimal("4.00") if sku == "PRD-005" else Decimal("45.00"))
                StockMovement.objects.create(product=obj, warehouse=warehouse, movement_type="IN", quantity=opening_qty, unit_cost=obj.cost_price, reference="OPENING-STOCK", notes="Demo opening stock")

        employee_data = [
            ("EMP-001", "Yasmine", "El Amrani", "Finance Manager", "Finance", "18500.00"),
            ("EMP-002", "Omar", "Bennani", "Sales Lead", "Sales", "16000.00"),
            ("EMP-003", "Salma", "Idrissi", "HR Specialist", "Human Resources", "12500.00"),
            ("EMP-004", "Mehdi", "Alaoui", "Warehouse Supervisor", "Operations", "11000.00"),
            ("EMP-005", "Nour", "Fassi", "Procurement Officer", "Procurement", "13200.00"),
            ("EMP-006", "Anas", "Tazi", "Sales Executive", "Sales", "9800.00"),
        ]
        for code, first, last, title, dept, salary in employee_data:
            Employee.objects.get_or_create(employee_code=code, defaults={"first_name": first, "last_name": last, "job_title": title, "department": departments[dept], "email": f"{first.lower()}.{last.lower()}@atlas-enterprise.local", "monthly_salary": Decimal(salary), "hire_date": date(2023, 3, 1)})

        # Bring opening inventory and the bank position into the ledger once.
        if not JournalEntry.objects.filter(reference="OPENING-INVENTORY-2026").exists():
            opening_inventory = sum((p.stock_value for p in products), Decimal("0.00"))
            if opening_inventory > 0:
                post_journal("OPENING-INVENTORY-2026", "Opening inventory position", [
                    ("1200", "Inventory", "ASSET", opening_inventory, 0, "Opening stock valuation"),
                    ("3000", "Owner Equity", "EQUITY", 0, opening_inventory, "Opening inventory equity"),
                ], actor=user, source_type="OPENING")

        if not JournalEntry.objects.filter(reference="OPENING-BANK-2026").exists():
            post_journal("OPENING-BANK-2026", "Opening bank position", [
                ("1010", "Bank", "ASSET", bank.opening_balance, 0, "Opening bank balance"),
                ("3000", "Owner Equity", "EQUITY", 0, bank.opening_balance, "Opening balance equity"),
            ], actor=user, source_type="OPENING")

        # Seed real, relational procurement/sales/expense flows only once.
        if not SalesOrder.objects.exists():
            create_purchase(supplier=suppliers[0], product=products[0], warehouse=warehouse,
                quantity=Decimal("15"), unit_cost=products[0].cost_price, actor=user)
            for idx in range(12):
                product = products[idx % len(products)]
                quantity = Decimal(str(1 + (idx % 3)))
                order, invoice = create_sale(customer=customers[idx % len(customers)], product=product,
                    warehouse=warehouse, quantity=quantity, unit_price=product.sale_price,
                    tax_rate=Decimal("20"), actor=user)
                # Spread the demo trend across recent months for an informative chart.
                month_offset = idx % 6
                month_index = timezone.localdate().year * 12 + timezone.localdate().month - 1 - month_offset
                year, month = month_index // 12, month_index % 12 + 1
                day = min(6 + (idx % 20), 26)
                stamp = timezone.make_aware(datetime.combine(date(year, month, day), time(11, 30)))
                SalesOrder.objects.filter(pk=order.pk).update(created_at=stamp)
                Invoice.objects.filter(pk=invoice.pk).update(issue_date=stamp.date(), created_at=stamp)
                if idx % 3 != 0:
                    record_payment(invoice=invoice, bank_account=bank, amount=(invoice.total * Decimal("0.5")).quantize(Decimal("0.01")), actor=user, reference=f"DEMO-PAY-{idx+1:03d}")
            create_expense(category="RENT", description="Monthly office rent", amount=Decimal("18500.00"), bank_account=bank, actor=user)
            create_expense(category="UTILITIES", description="Utilities and connectivity", amount=Decimal("3250.00"), bank_account=bank, actor=user)
            create_expense(category="MARKETING", description="Quarterly marketing campaign", amount=Decimal("7200.00"), bank_account=bank, actor=user)

        if not PayrollRun.objects.filter(period=timezone.localdate().strftime("%Y-%m")).exists():
            create_payroll_run(period=timezone.localdate().strftime("%Y-%m"), actor=user)

        self.stdout.write(self.style.SUCCESS("Enterprise 360 demo data is ready."))
        self.stdout.write("Login: admin")
        self.stdout.write("Password: ENTERPRISE_ADMIN_PASSWORD if set; otherwise Admin12345!")
        self.stdout.write("Company: Atlas Enterprise Group · Currency: MAD")
