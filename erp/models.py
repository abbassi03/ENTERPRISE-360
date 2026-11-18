from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Company(TimeStampedModel):
    name = models.CharField(max_length=160)
    legal_name = models.CharField(max_length=180, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    tax_number = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=3, default="MAD")

    def __str__(self):
        return self.name


class Department(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(TimeStampedModel):
    STATUS_CHOICES = [("ACTIVE", "Active"), ("ON_LEAVE", "On leave"), ("INACTIVE", "Inactive")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee_profile")
    employee_code = models.CharField(max_length=24, unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees")
    job_title = models.CharField(max_length=100, blank=True)
    hire_date = models.DateField(default=timezone.localdate)
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return str(self)


class Customer(TimeStampedModel):
    STATUS_CHOICES = [("ACTIVE", "Active"), ("LEAD", "Lead"), ("INACTIVE", "Inactive")]
    customer_code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    city = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    tax_number = models.CharField(max_length=80, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def outstanding_balance(self):
        invoices = self.invoices.filter(invoice_type="SALES", status__in=["ISSUED", "PARTIAL", "OVERDUE"])
        return sum((invoice.balance_due for invoice in invoices), Decimal("0.00"))


class Supplier(TimeStampedModel):
    STATUS_CHOICES = [("ACTIVE", "Active"), ("INACTIVE", "Inactive")]
    supplier_code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    city = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    tax_number = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Warehouse(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    location = models.CharField(max_length=160, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    CATEGORY_CHOICES = [("ELECTRONICS", "Electronics"), ("OFFICE", "Office"), ("FURNITURE", "Furniture"), ("SERVICES", "Services"), ("OTHER", "Other")]
    sku = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="OTHER")
    description = models.TextField(blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("5.00"))
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.sku} · {self.name}"

    def stock_at(self, warehouse=None):
        movements = self.stock_movements.all()
        if warehouse is not None:
            movements = movements.filter(warehouse=warehouse)
        incoming = movements.filter(movement_type="IN").aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")
        outgoing = movements.filter(movement_type="OUT").aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")
        return incoming - outgoing

    @property
    def stock_quantity(self):
        return self.stock_at()

    @property
    def stock_value(self):
        return self.stock_quantity * self.cost_price

    @property
    def stock_status(self):
        if self.stock_quantity <= 0:
            return "OUT"
        if self.stock_quantity <= self.reorder_level:
            return "LOW"
        return "HEALTHY"


class StockMovement(TimeStampedModel):
    TYPE_CHOICES = [("IN", "Stock in"), ("OUT", "Stock out"), ("ADJUSTMENT", "Adjustment")]
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_movements")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reference = models.CharField(max_length=80, blank=True)
    notes = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})

    def __str__(self):
        return f"{self.movement_type} {self.product.sku} × {self.quantity}"


class SalesOrder(TimeStampedModel):
    STATUS_CHOICES = [("CONFIRMED", "Confirmed"), ("FULFILLED", "Fulfilled"), ("CANCELLED", "Cancelled")]
    number = models.CharField(max_length=32, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_orders")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="CONFIRMED")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class SalesOrderItem(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=14, decimal_places=2)


class PurchaseOrder(TimeStampedModel):
    STATUS_CHOICES = [("RECEIVED", "Received"), ("CANCELLED", "Cancelled")]
    number = models.CharField(max_length=32, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="RECEIVED")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)


class Invoice(TimeStampedModel):
    TYPE_CHOICES = [("SALES", "Sales invoice"), ("PURCHASE", "Purchase invoice")]
    STATUS_CHOICES = [("DRAFT", "Draft"), ("ISSUED", "Issued"), ("PARTIAL", "Partially paid"), ("PAID", "Paid"), ("OVERDUE", "Overdue")]
    number = models.CharField(max_length=32, unique=True)
    invoice_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="invoices")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.PROTECT, related_name="invoices")
    sales_order = models.OneToOneField(SalesOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="invoice")
    purchase_order = models.OneToOneField(PurchaseOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="invoice")
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(default=timezone.localdate)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ISSUED")

    class Meta:
        ordering = ["-issue_date", "-created_at"]

    @property
    def paid_total(self):
        return self.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def balance_due(self):
        return max(Decimal("0.00"), self.total - self.paid_total)

    @property
    def party_name(self):
        return self.customer.name if self.customer_id else (self.supplier.name if self.supplier_id else "—")


class BankAccount(TimeStampedModel):
    name = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=100, blank=True)
    account_number_masked = models.CharField(max_length=40, blank=True)
    currency = models.CharField(max_length=3, default="MAD")
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    @property
    def current_balance(self):
        credits = self.transactions.filter(direction="IN").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        debits = self.transactions.filter(direction="OUT").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return self.opening_balance + credits - debits


class BankTransaction(TimeStampedModel):
    DIRECTION_CHOICES = [("IN", "Money in"), ("OUT", "Money out")]
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="transactions")
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=80, blank=True)
    description = models.CharField(max_length=200)

    class Meta:
        ordering = ["-created_at"]


class Payment(TimeStampedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=80, blank=True)
    received_on = models.DateField(default=timezone.localdate)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class Expense(TimeStampedModel):
    CATEGORY_CHOICES = [("RENT", "Rent"), ("UTILITIES", "Utilities"), ("TRAVEL", "Travel"), ("SUPPLIES", "Supplies"), ("MARKETING", "Marketing"), ("PAYROLL", "Payroll"), ("OTHER", "Other")]
    reference = models.CharField(max_length=32, unique=True)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default="OTHER")
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="expenses")
    expense_date = models.DateField(default=timezone.localdate)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-expense_date", "-created_at"]


class Account(TimeStampedModel):
    TYPE_CHOICES = [("ASSET", "Asset"), ("LIABILITY", "Liability"), ("EQUITY", "Equity"), ("REVENUE", "Revenue"), ("EXPENSE", "Expense")]
    code = models.CharField(max_length=12, unique=True)
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class JournalEntry(TimeStampedModel):
    reference = models.CharField(max_length=40, unique=True)
    entry_date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=200)
    source_type = models.CharField(max_length=30, blank=True)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    posted = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-entry_date", "-created_at"]

    @property
    def debit_total(self):
        return self.lines.aggregate(total=Sum("debit"))["total"] or Decimal("0.00")

    @property
    def credit_total(self):
        return self.lines.aggregate(total=Sum("credit"))["total"] or Decimal("0.00")

    @property
    def is_balanced(self):
        return self.debit_total == self.credit_total


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="journal_lines")
    description = models.CharField(max_length=160, blank=True)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    def clean(self):
        if self.debit < 0 or self.credit < 0:
            raise ValidationError("Debit and credit values cannot be negative.")
        if self.debit and self.credit:
            raise ValidationError("A journal line cannot contain both debit and credit.")


class PayrollRun(TimeStampedModel):
    STATUS_CHOICES = [("DRAFT", "Draft"), ("APPROVED", "Approved"), ("PAID", "Paid")]
    period = models.CharField(max_length=7, help_text="YYYY-MM")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="DRAFT")
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-period"]


class Payslip(TimeStampedModel):
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payslips")
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = [("payroll_run", "employee")]


class AuditLog(TimeStampedModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)
    entity = models.CharField(max_length=60)
    entity_id = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=240)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
