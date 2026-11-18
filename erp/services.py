from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    Account, AuditLog, BankAccount, BankTransaction, Customer, Employee, Expense,
    Invoice, JournalEntry, JournalLine, Payment, PayrollRun, Payslip, Product, PurchaseOrder,
    PurchaseOrderItem, SalesOrder, SalesOrderItem, StockMovement, Supplier,
)

MONEY = Decimal("0.01")

def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)

def make_reference(prefix):
    return f"{prefix}-{timezone.localdate():%y%m%d}-{uuid4().hex[:6].upper()}"

def audit(actor, action, entity, entity_id, description, request=None):
    ip = None
    if request is not None:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    AuditLog.objects.create(actor=actor if getattr(actor, "is_authenticated", False) else None,
                            action=action, entity=entity, entity_id=str(entity_id or ""),
                            description=description[:240], ip_address=ip or None)

def account(code, name, account_type):
    obj, _ = Account.objects.get_or_create(code=code, defaults={"name": name, "account_type": account_type})
    return obj

def post_journal(reference, description, lines, actor=None, source_type="", source_id=None):
    """Create a balanced, immutable-by-convention journal entry."""
    normalized = []
    debit_total = Decimal("0.00")
    credit_total = Decimal("0.00")
    for code, name, account_type, debit, credit, line_description in lines:
        debit, credit = money(debit), money(credit)
        if debit < 0 or credit < 0 or (debit and credit):
            raise ValidationError("Each journal line must contain one non-negative debit or credit.")
        normalized.append((account(code, name, account_type), debit, credit, line_description))
        debit_total += debit
        credit_total += credit
    if not normalized or money(debit_total) != money(credit_total):
        raise ValidationError(f"Unbalanced journal entry: debit {debit_total} / credit {credit_total}.")
    entry = JournalEntry.objects.create(reference=reference, description=description,
        source_type=source_type, source_id=source_id,
        created_by=actor if getattr(actor, "is_authenticated", False) else None)
    JournalLine.objects.bulk_create([
        JournalLine(entry=entry, account=acct, debit=debit, credit=credit, description=desc)
        for acct, debit, credit, desc in normalized
    ])
    return entry

@transaction.atomic
def create_sale(*, customer, product, warehouse, quantity, unit_price, tax_rate=Decimal("20.00"), actor=None, request=None):
    quantity, unit_price, tax_rate = Decimal(quantity), money(unit_price), Decimal(tax_rate)
    if quantity <= 0 or unit_price < 0 or tax_rate < 0 or tax_rate > 100:
        raise ValidationError("Enter a positive quantity, a valid price, and a tax rate between 0 and 100.")
    product = Product.objects.select_for_update().get(pk=product.pk)
    available = product.stock_at(warehouse)
    if available < quantity:
        raise ValidationError(f"Insufficient stock for {product.name}. Available: {available}.")
    subtotal = money(quantity * unit_price)
    tax_amount = money(subtotal * tax_rate / Decimal("100"))
    total = subtotal + tax_amount
    number = make_reference("SO")
    order = SalesOrder.objects.create(number=number, customer=customer, subtotal=subtotal,
        tax_amount=tax_amount, total=total, created_by=actor if getattr(actor, "is_authenticated", False) else None)
    captured_unit_cost = money(product.cost_price)
    SalesOrderItem.objects.create(order=order, product=product, warehouse=warehouse,
        quantity=quantity, unit_price=unit_price, unit_cost=captured_unit_cost, line_total=subtotal)
    StockMovement.objects.create(product=product, warehouse=warehouse, movement_type="OUT",
        quantity=quantity, unit_cost=product.cost_price, reference=number,
        notes=f"Sale to {customer.name}", created_by=actor if getattr(actor, "is_authenticated", False) else None)
    invoice = Invoice.objects.create(number=make_reference("INV"), invoice_type="SALES", customer=customer,
        sales_order=order, subtotal=subtotal, tax_amount=tax_amount, total=total,
        issue_date=timezone.localdate(), due_date=timezone.localdate() + timedelta(days=30))
    post_journal(make_reference("JE"), f"Sales invoice {invoice.number}", [
        ("1100", "Accounts Receivable", "ASSET", total, 0, "Customer receivable"),
        ("4000", "Sales Revenue", "REVENUE", 0, subtotal, "Product sales"),
        ("2100", "VAT Payable", "LIABILITY", 0, tax_amount, "Output VAT"),
    ], actor=actor, source_type="SALES", source_id=order.pk)
    cogs = money(quantity * captured_unit_cost)
    if cogs:
        post_journal(make_reference("JE"), f"Cost of goods sold {order.number}", [
            ("5000", "Cost of Goods Sold", "EXPENSE", cogs, 0, "Cost attached to dispatched stock"),
            ("1200", "Inventory", "ASSET", 0, cogs, "Inventory issued to customer"),
        ], actor=actor, source_type="COGS", source_id=order.pk)
    audit(actor, "CREATE", "SalesOrder", order.pk, f"Created {order.number} for {customer.name}", request)
    return order, invoice

@transaction.atomic
def create_purchase(*, supplier, product, warehouse, quantity, unit_cost, tax_rate=Decimal("20.00"), actor=None, request=None):
    quantity, unit_cost, tax_rate = Decimal(quantity), money(unit_cost), Decimal(tax_rate)
    if quantity <= 0 or unit_cost < 0 or tax_rate < 0 or tax_rate > 100:
        raise ValidationError("Enter a positive quantity, a valid unit cost, and a tax rate between 0 and 100.")
    product = Product.objects.select_for_update().get(pk=product.pk)
    subtotal = money(quantity * unit_cost)
    tax_amount = money(subtotal * tax_rate / Decimal("100"))
    total = subtotal + tax_amount
    number = make_reference("PO")
    order = PurchaseOrder.objects.create(number=number, supplier=supplier, warehouse=warehouse,
        subtotal=subtotal, tax_amount=tax_amount, total=total,
        created_by=actor if getattr(actor, "is_authenticated", False) else None)
    PurchaseOrderItem.objects.create(order=order, product=product, quantity=quantity,
        unit_cost=unit_cost, line_total=subtotal)
    StockMovement.objects.create(product=product, warehouse=warehouse, movement_type="IN",
        quantity=quantity, unit_cost=unit_cost, reference=number,
        notes=f"Purchase from {supplier.name}", created_by=actor if getattr(actor, "is_authenticated", False) else None)
    # Moving weighted average cost is more useful than simply replacing the existing cost.
    existing_qty = product.stock_quantity - quantity
    if existing_qty > 0:
        product.cost_price = money(((existing_qty * product.cost_price) + (quantity * unit_cost)) / (existing_qty + quantity))
    else:
        product.cost_price = unit_cost
    product.save(update_fields=["cost_price", "updated_at"])
    invoice = Invoice.objects.create(number=make_reference("BILL"), invoice_type="PURCHASE", supplier=supplier,
        purchase_order=order, subtotal=subtotal, tax_amount=tax_amount, total=total,
        issue_date=timezone.localdate(), due_date=timezone.localdate() + timedelta(days=30))
    post_journal(make_reference("JE"), f"Supplier bill {invoice.number}", [
        ("1200", "Inventory", "ASSET", subtotal, 0, "Inventory received"),
        ("1400", "VAT Recoverable", "ASSET", tax_amount, 0, "Input VAT"),
        ("2000", "Accounts Payable", "LIABILITY", 0, total, "Supplier payable"),
    ], actor=actor, source_type="PURCHASE", source_id=order.pk)
    audit(actor, "CREATE", "PurchaseOrder", order.pk, f"Received {order.number} from {supplier.name}", request)
    return order, invoice

@transaction.atomic
def record_payment(*, invoice, bank_account, amount, actor=None, request=None, reference=""):
    amount = money(amount)
    if amount <= 0:
        raise ValidationError("Payment amount must be greater than zero.")
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if amount > invoice.balance_due:
        raise ValidationError(f"Payment exceeds the outstanding balance ({invoice.balance_due}).")
    if not bank_account.active:
        raise ValidationError("Selected bank account is inactive.")
    payment = Payment.objects.create(invoice=invoice, bank_account=bank_account, amount=amount,
        reference=reference or make_reference("PAY"), received_by=actor if getattr(actor, "is_authenticated", False) else None)
    direction = "IN" if invoice.invoice_type == "SALES" else "OUT"
    BankTransaction.objects.create(bank_account=bank_account, direction=direction, amount=amount,
        reference=payment.reference, description=f"Payment for {invoice.number}")
    if invoice.invoice_type == "SALES":
        lines = [
            ("1010", "Bank", "ASSET", amount, 0, "Bank receipt"),
            ("1100", "Accounts Receivable", "ASSET", 0, amount, "Receivable settled"),
        ]
    else:
        lines = [
            ("2000", "Accounts Payable", "LIABILITY", amount, 0, "Supplier payable settled"),
            ("1010", "Bank", "ASSET", 0, amount, "Bank payment"),
        ]
    post_journal(make_reference("JE"), f"Payment {payment.reference}", lines, actor=actor,
                 source_type="PAYMENT", source_id=payment.pk)
    invoice.refresh_from_db()
    if invoice.balance_due == 0:
        invoice.status = "PAID"
    elif invoice.paid_total > 0:
        invoice.status = "PARTIAL"
    invoice.save(update_fields=["status", "updated_at"])
    audit(actor, "PAYMENT", "Invoice", invoice.pk, f"Recorded {amount} against {invoice.number}", request)
    return payment

@transaction.atomic
def create_expense(*, category, description, amount, bank_account, expense_date=None, actor=None, request=None):
    amount = money(amount)
    if amount <= 0:
        raise ValidationError("Expense amount must be greater than zero.")
    if not bank_account.active:
        raise ValidationError("Selected bank account is inactive.")
    expense = Expense.objects.create(reference=make_reference("EXP"), category=category,
        description=description, amount=amount, bank_account=bank_account,
        expense_date=expense_date or timezone.localdate(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None)
    expense_accounts = {
        "RENT": ("5100", "Rent Expense"), "UTILITIES": ("5200", "Utilities Expense"),
        "TRAVEL": ("5300", "Travel Expense"), "SUPPLIES": ("5400", "Office Supplies Expense"),
        "MARKETING": ("5500", "Marketing Expense"), "PAYROLL": ("6000", "Salaries Expense"),
        "OTHER": ("5900", "Other Operating Expense"),
    }
    code, name = expense_accounts.get(category, expense_accounts["OTHER"])
    BankTransaction.objects.create(bank_account=bank_account, direction="OUT", amount=amount,
        reference=expense.reference, description=description)
    post_journal(make_reference("JE"), f"Expense {expense.reference}", [
        (code, name, "EXPENSE", amount, 0, description),
        ("1010", "Bank", "ASSET", 0, amount, "Bank payment"),
    ], actor=actor, source_type="EXPENSE", source_id=expense.pk)
    audit(actor, "CREATE", "Expense", expense.pk, f"Recorded expense {expense.reference}", request)
    return expense

@transaction.atomic
def create_payroll_run(*, period, actor=None, request=None):
    if PayrollRun.objects.filter(period=period).exists():
        raise ValidationError(f"Payroll for {period} already exists.")
    employees = Employee.objects.filter(status="ACTIVE").select_related("department")
    if not employees.exists():
        raise ValidationError("There are no active employees to include in payroll.")
    run = PayrollRun.objects.create(period=period, created_by=actor if getattr(actor, "is_authenticated", False) else None)
    gross_total = deductions_total = net_total = Decimal("0.00")
    slips = []
    for employee in employees:
        gross = money(employee.monthly_salary)
        deductions = money(gross * Decimal("0.05"))  # Demo withholding only; not a statutory payroll calculation.
        net = gross - deductions
        slips.append(Payslip(payroll_run=run, employee=employee, gross_salary=gross,
                             deductions=deductions, net_salary=net))
        gross_total += gross
        deductions_total += deductions
        net_total += net
    Payslip.objects.bulk_create(slips)
    run.total_gross, run.total_deductions, run.total_net = gross_total, deductions_total, net_total
    run.save(update_fields=["total_gross", "total_deductions", "total_net", "updated_at"])
    post_journal(make_reference("JE"), f"Payroll accrual {period}", [
        ("6000", "Salaries Expense", "EXPENSE", gross_total, 0, "Gross payroll"),
        ("2200", "Salaries Payable", "LIABILITY", 0, net_total, "Net salaries payable"),
        ("2110", "Payroll Deductions Payable", "LIABILITY", 0, deductions_total, "Demo payroll deductions"),
    ], actor=actor, source_type="PAYROLL", source_id=run.pk)
    audit(actor, "CREATE", "PayrollRun", run.pk, f"Created payroll run for {period}", request)
    return run
