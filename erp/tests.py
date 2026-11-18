from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import (BankAccount, BankTransaction, Customer, Invoice, JournalEntry,
                     Product, StockMovement, Supplier, Warehouse, Expense)
from .services import create_expense, create_purchase, create_sale, record_payment

User = get_user_model()

class EnterpriseWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="StrongPass!234")
        self.customer = Customer.objects.create(customer_code="CUS-T", name="Test Customer")
        self.supplier = Supplier.objects.create(supplier_code="SUP-T", name="Test Supplier")
        self.warehouse = Warehouse.objects.create(code="WH-T", name="Test Warehouse")
        self.product = Product.objects.create(sku="SKU-T", name="Test Product", cost_price=Decimal("40.00"), sale_price=Decimal("75.00"), reorder_level=Decimal("2.00"))
        self.bank = BankAccount.objects.create(name="Test Bank", opening_balance=Decimal("1000.00"))
        StockMovement.objects.create(product=self.product, warehouse=self.warehouse, movement_type="IN", quantity=Decimal("10.00"), unit_cost=Decimal("40.00"), reference="OPENING-T")

    def test_sale_reduces_stock_creates_invoice_and_balanced_ledger(self):
        order, invoice = create_sale(customer=self.customer, product=self.product, warehouse=self.warehouse,
            quantity=Decimal("2"), unit_price=Decimal("75"), actor=self.user)
        self.assertEqual(self.product.stock_quantity, Decimal("8.00"))
        self.assertEqual(invoice.total, Decimal("180.00"))
        entries = JournalEntry.objects.filter(source_id=order.pk)
        self.assertEqual(entries.count(), 2)  # revenue and cost-of-goods-sold
        self.assertTrue(all(entry.is_balanced for entry in entries))

    def test_sale_rejects_insufficient_stock_without_partial_records(self):
        with self.assertRaises(ValidationError):
            create_sale(customer=self.customer, product=self.product, warehouse=self.warehouse,
                quantity=Decimal("99"), unit_price=Decimal("75"), actor=self.user)
        self.assertEqual(self.product.stock_quantity, Decimal("10.00"))
        self.assertEqual(Invoice.objects.count(), 0)

    def test_purchase_increases_stock_and_creates_payable_invoice(self):
        before = self.product.stock_quantity
        order, invoice = create_purchase(supplier=self.supplier, product=self.product, warehouse=self.warehouse,
            quantity=Decimal("5"), unit_cost=Decimal("38"), actor=self.user)
        self.assertEqual(self.product.stock_quantity, before + Decimal("5"))
        self.assertEqual(invoice.invoice_type, "PURCHASE")
        self.assertTrue(all(e.is_balanced for e in JournalEntry.objects.filter(source_id=order.pk)))

    def test_payment_updates_invoice_and_bank_balance(self):
        _, invoice = create_sale(customer=self.customer, product=self.product, warehouse=self.warehouse,
            quantity=Decimal("1"), unit_price=Decimal("75"), actor=self.user)
        before = self.bank.current_balance
        record_payment(invoice=invoice, bank_account=self.bank, amount=invoice.total, actor=self.user)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "PAID")
        self.assertEqual(invoice.balance_due, Decimal("0.00"))
        self.assertEqual(self.bank.current_balance, before + invoice.total)

    def test_expense_updates_bank_and_journal(self):
        before = self.bank.current_balance
        expense = create_expense(category="UTILITIES", description="Internet", amount=Decimal("120"), bank_account=self.bank, actor=self.user)
        self.assertEqual(expense.amount, Decimal("120.00"))
        self.assertEqual(self.bank.current_balance, before - Decimal("120.00"))
        entry = JournalEntry.objects.get(source_type="EXPENSE", source_id=expense.pk)
        self.assertTrue(entry.is_balanced)

    def test_dashboard_redirects_anonymous_users_to_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts/login", response.url)

    def test_non_staff_user_cannot_open_write_workflow(self):
        self.client.force_login(self.user)
        response = self.client.get("/sales/new/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_customer_csv_escapes_spreadsheet_formulas(self):
        Customer.objects.create(customer_code="CUS-X", name="=HYPERLINK(\"https://example.com\")")
        self.client.force_login(self.user)
        response = self.client.get("/exports/customers/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.content.decode("utf-8-sig"))
