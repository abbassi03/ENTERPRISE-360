import csv
import json
from functools import wraps
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Count, F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (BankAccountForm, CompanyForm, CustomerForm, EmployeeForm, ExpenseForm,
                    PaymentForm, PayrollForm, ProductForm, PurchaseForm, SalesForm, SupplierForm)
from .models import (Account, AuditLog, BankAccount, BankTransaction, Company, Customer,
                     Department, Employee, Expense, Invoice, JournalEntry, Product,
                     PurchaseOrder, SalesOrder, StockMovement, Supplier, Warehouse,
                     PayrollRun, Payslip, SalesOrderItem)
from .services import (audit, create_expense, create_payroll_run, create_purchase,
                       create_sale, record_payment)



def staff_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, "This action requires staff permission. Contact your workspace administrator.")
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)
    return _wrapped


def _ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def _money(value):
    return Decimal(value or 0)


def _month_start(year, month):
    return date(year, month, 1)


def _shift_month(d, offset):
    index = d.year * 12 + d.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


@login_required
def dashboard(request):
    today = timezone.localdate()
    month_start = _month_start(today.year, today.month)
    revenue = SalesOrder.objects.exclude(status="CANCELLED").aggregate(total=Sum("subtotal"))["total"] or Decimal("0.00")
    month_revenue = SalesOrder.objects.exclude(status="CANCELLED").filter(created_at__date__gte=month_start).aggregate(total=Sum("subtotal"))["total"] or Decimal("0.00")
    cash_expenses = Expense.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    payroll_expenses = PayrollRun.objects.aggregate(total=Sum("total_gross"))["total"] or Decimal("0.00")
    expenses_total = cash_expenses + payroll_expenses
    cogs_total = SalesOrderItem.objects.aggregate(total=Sum(F("quantity") * F("unit_cost")))["total"] or Decimal("0.00")
    cash_total = sum((account.current_balance for account in BankAccount.objects.filter(active=True)), Decimal("0.00"))
    receivables = sum((invoice.balance_due for invoice in Invoice.objects.filter(invoice_type="SALES", status__in=["ISSUED", "PARTIAL", "OVERDUE"])), Decimal("0.00"))
    payables = sum((invoice.balance_due for invoice in Invoice.objects.filter(invoice_type="PURCHASE", status__in=["ISSUED", "PARTIAL", "OVERDUE"])), Decimal("0.00"))
    products = list(Product.objects.filter(active=True))
    stock_value = sum((product.stock_value for product in products), Decimal("0.00"))
    low_stock = [product for product in products if product.stock_status in {"LOW", "OUT"}]

    chart_labels, chart_sales, chart_expenses = [], [], []
    for offset in range(-5, 1):
        start = _shift_month(month_start, offset)
        end = _shift_month(start, 1)
        sales_value = SalesOrder.objects.exclude(status="CANCELLED").filter(created_at__date__gte=start, created_at__date__lt=end).aggregate(total=Sum("subtotal"))["total"] or Decimal("0.00")
        expense_value = Expense.objects.filter(expense_date__gte=start, expense_date__lt=end).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        payroll_value = PayrollRun.objects.filter(period=start.strftime("%Y-%m")).aggregate(total=Sum("total_gross"))["total"] or Decimal("0.00")
        expense_value += payroll_value
        chart_labels.append(start.strftime("%b %y"))
        chart_sales.append(float(sales_value))
        chart_expenses.append(float(expense_value))

    category_rows = list(Product.objects.filter(active=True).values("category").annotate(total=Sum("salesorderitem__line_total")).order_by("category"))
    category_labels = [row["category"].replace("_", " ").title() for row in category_rows if row["total"]]
    category_values = [float(row["total"] or 0) for row in category_rows if row["total"]]
    invoice_counts = [Invoice.objects.filter(status=status).count() for status in ["PAID", "ISSUED", "PARTIAL", "OVERDUE"]]
    invoice_labels = ["Paid", "Unpaid", "Partial", "Overdue"]

    recent_sales = SalesOrder.objects.select_related("customer").all()[:6]
    recent_activity = AuditLog.objects.select_related("actor").all()[:6]
    context = {
        "page_title": "Executive overview", "today": today,
        "kpis": [
            {"label": "Total revenue", "value": revenue, "note": f"{month_revenue:,.2f} this month", "tone": "violet", "icon": "↗"},
            {"label": "Operating expenses", "value": expenses_total, "note": "Recorded expenses", "tone": "rose", "icon": "↘"},
            {"label": "Cash & banks", "value": cash_total, "note": f"{BankAccount.objects.filter(active=True).count()} active accounts", "tone": "teal", "icon": "▤"},
            {"label": "Receivables", "value": receivables, "note": f"{Invoice.objects.filter(invoice_type='SALES', status__in=['ISSUED','PARTIAL','OVERDUE']).count()} open invoices", "tone": "amber", "icon": "◷"},
        ],
        "secondary_kpis": [
            {"label": "Gross profit", "value": (SalesOrder.objects.exclude(status="CANCELLED").aggregate(total=Sum("subtotal"))["total"] or Decimal("0.00")) - cogs_total, "icon": "✦"},
            {"label": "Inventory value", "value": stock_value, "icon": "▦"},
            {"label": "Supplier payables", "value": payables, "icon": "⇄"},
            {"label": "Active employees", "value": Employee.objects.filter(status="ACTIVE").count(), "icon": "♙", "plain": True},
        ],
        "chart_data": json.dumps({"labels": chart_labels, "sales": chart_sales, "expenses": chart_expenses,
                                  "categoryLabels": category_labels, "categoryValues": category_values,
                                  "invoiceLabels": invoice_labels, "invoiceValues": invoice_counts}),
        "recent_sales": recent_sales, "recent_activity": recent_activity,
        "low_stock": low_stock[:6], "low_stock_count": len(low_stock), "category_has_data": bool(category_values),
        "sales_count": SalesOrder.objects.count(), "customer_count": Customer.objects.count(),
        "supplier_count": Supplier.objects.count(), "product_count": Product.objects.count(),
    }
    return render(request, "erp/dashboard.html", context)


def _render_table(request, *, title, eyebrow, description, add_url, headers, records, icon="◈", export_url=None):
    return render(request, "erp/list.html", {
        "page_title": title, "eyebrow": eyebrow, "description": description,
        "add_url": add_url, "headers": headers, "records": records,
        "icon": icon, "export_url": export_url,
    })

@login_required
def customers(request):
    q = request.GET.get("q", "").strip()
    qs = Customer.objects.all()
    if q:
        qs = qs.filter(name__icontains=q) | qs.filter(customer_code__icontains=q) | qs.filter(email__icontains=q)
    records = [{"primary": x.name, "secondary": x.customer_code, "cells": [x.email or "—", x.phone or "—", x.city or "—", f"{x.credit_limit:,.2f} · {x.outstanding_balance:,.2f}"], "tag": x.get_status_display(), "tag_class": "success" if x.status == "ACTIVE" else "muted", "action_url": reverse("customer-edit", args=[x.pk]), "action_label": "Edit"} for x in qs[:150]]
    return _render_table(request, title="Customers", eyebrow="RELATIONSHIP MANAGEMENT", description="Manage customer profiles, credit limits and account balances.", add_url=reverse("customer-create"), headers=["Email", "Phone", "City", "Credit limit · Balance"], records=records, icon="◎", export_url=reverse("export-data", args=["customers"]))

@login_required
def suppliers(request):
    q = request.GET.get("q", "").strip()
    qs = Supplier.objects.all()
    if q:
        qs = qs.filter(name__icontains=q) | qs.filter(supplier_code__icontains=q)
    records = [{"primary": x.name, "secondary": x.supplier_code, "cells": [x.contact_name or "—", x.email or "—", x.phone or "—", x.city or "—"], "tag": x.get_status_display(), "tag_class": "success" if x.status == "ACTIVE" else "muted", "action_url": reverse("supplier-edit", args=[x.pk]), "action_label": "Edit"} for x in qs[:150]]
    return _render_table(request, title="Suppliers", eyebrow="PROCUREMENT", description="Maintain supplier contacts and sourcing relationships.", add_url=reverse("supplier-create"), headers=["Contact", "Email", "Phone", "City"], records=records, icon="◇", export_url=reverse("export-data", args=["suppliers"]))

@login_required
def products(request):
    q = request.GET.get("q", "").strip()
    qs = Product.objects.all()
    if q:
        qs = qs.filter(name__icontains=q) | qs.filter(sku__icontains=q)
    records = []
    for x in qs[:150]:
        stock = x.stock_quantity
        records.append({"primary": x.name, "secondary": x.sku, "cells": [x.get_category_display(), f"{x.sale_price:,.2f}", f"{stock:,.2f}", f"{x.stock_value:,.2f}"], "tag": {"HEALTHY": "Healthy", "LOW": "Low stock", "OUT": "Out of stock"}[x.stock_status], "tag_class": {"HEALTHY": "success", "LOW": "warning", "OUT": "danger"}[x.stock_status], "action_url": reverse("product-edit", args=[x.pk]), "action_label": "Edit"})
    return _render_table(request, title="Products & inventory", eyebrow="OPERATIONS", description="Track product catalogue, stock availability and inventory value.", add_url=reverse("product-create"), headers=["Category", "Sale price", "On hand", "Stock value"], records=records, icon="▦", export_url=reverse("export-data", args=["products"]))

@login_required
def employees(request):
    q = request.GET.get("q", "").strip()
    qs = Employee.objects.select_related("department").all()
    if q:
        qs = qs.filter(first_name__icontains=q) | qs.filter(last_name__icontains=q) | qs.filter(employee_code__icontains=q)
    records = [{"primary": x.full_name, "secondary": x.employee_code, "cells": [x.job_title or "—", x.department.name if x.department else "—", x.email or "—", f"{x.monthly_salary:,.2f}"], "tag": x.get_status_display(), "tag_class": "success" if x.status == "ACTIVE" else "muted", "action_url": reverse("employee-edit", args=[x.pk]), "action_label": "Edit"} for x in qs[:150]]
    return _render_table(request, title="People & employees", eyebrow="HUMAN RESOURCES", description="Employee directory, departments and compensation overview.", add_url=reverse("employee-create"), headers=["Job title", "Department", "Email", "Monthly salary"], records=records, icon="♙")

@login_required
def sales(request):
    qs = SalesOrder.objects.select_related("customer").all()[:150]
    records = [{"primary": x.number, "secondary": x.customer.name, "cells": [x.created_at.strftime("%d %b %Y"), f"{x.subtotal:,.2f}", f"{x.tax_amount:,.2f}", f"{x.total:,.2f}"], "tag": x.get_status_display(), "tag_class": "success" if x.status != "CANCELLED" else "danger"} for x in qs]
    return _render_table(request, title="Sales orders", eyebrow="REVENUE CYCLE", description="Create sales, reserve available stock and issue a customer invoice in one transaction.", add_url=reverse("sale-create"), headers=["Date", "Subtotal", "Tax", "Total"], records=records, icon="↗", export_url=reverse("export-data", args=["sales"]))

@login_required
def purchases(request):
    qs = PurchaseOrder.objects.select_related("supplier", "warehouse").all()[:150]
    records = [{"primary": x.number, "secondary": x.supplier.name, "cells": [x.created_at.strftime("%d %b %Y"), x.warehouse.name, f"{x.subtotal:,.2f}", f"{x.total:,.2f}"], "tag": x.get_status_display(), "tag_class": "success"} for x in qs]
    return _render_table(request, title="Purchase orders", eyebrow="PROCUREMENT", description="Record supplier purchases and receive quantities into warehouse stock.", add_url=reverse("purchase-create"), headers=["Date", "Warehouse", "Subtotal", "Total"], records=records, icon="⇄", export_url=reverse("export-data", args=["purchases"]))

@login_required
def invoices(request):
    qs = Invoice.objects.select_related("customer", "supplier").all()[:150]
    records = []
    for x in qs:
        due = x.balance_due
        status = "Overdue" if due > 0 and x.due_date < timezone.localdate() else x.get_status_display()
        tag_class = "success" if due == 0 else ("danger" if status == "Overdue" else "warning")
        records.append({"primary": x.number, "secondary": f"{x.get_invoice_type_display()} · {x.party_name}", "cells": [x.issue_date.strftime("%d %b %Y"), x.due_date.strftime("%d %b %Y"), f"{x.total:,.2f}", f"{due:,.2f}"], "tag": status, "tag_class": tag_class, "action_url": reverse("payment-create") + f"?invoice={x.pk}" if due > 0 else "", "action_label": "Record payment" if due > 0 else "Settled"})
    return _render_table(request, title="Invoices & collections", eyebrow="FINANCE", description="Monitor customer receivables and supplier payables. Record partial or full settlements.", add_url=reverse("payment-create"), headers=["Issued", "Due date", "Invoice total", "Balance due"], records=records, icon="▤")

@login_required
def expenses(request):
    qs = Expense.objects.select_related("bank_account").all()[:150]
    records = [{"primary": x.reference, "secondary": x.description, "cells": [x.get_category_display(), x.expense_date.strftime("%d %b %Y"), x.bank_account.name, f"{x.amount:,.2f}"], "tag": "Paid", "tag_class": "success"} for x in qs]
    return _render_table(request, title="Expenses", eyebrow="COST CONTROL", description="Track operating costs with automatic bank and general-ledger entries.", add_url=reverse("expense-create"), headers=["Category", "Date", "Paid from", "Amount"], records=records, icon="↘", export_url=reverse("export-data", args=["expenses"]))

@login_required
def finance(request):
    banks = BankAccount.objects.filter(active=True)
    entries = JournalEntry.objects.prefetch_related("lines__account").all()[:12]
    return render(request, "erp/finance.html", {"page_title": "Finance & accounting", "banks": banks, "entries": entries, "transactions": BankTransaction.objects.select_related("bank_account").all()[:12], "add_url": reverse("bank-create")})

@login_required
def payroll(request):
    runs = PayrollRun.objects.prefetch_related("payslips").all()[:24]
    return render(request, "erp/payroll.html", {"page_title": "Payroll management", "form": PayrollForm(initial={"period": timezone.localdate().strftime("%Y-%m")}), "runs": runs, "employees_count": Employee.objects.filter(status="ACTIVE").count()})

@login_required
def reports(request):
    total_sales = SalesOrder.objects.exclude(status="CANCELLED").aggregate(total=Sum("subtotal"))["total"] or Decimal("0")
    total_expenses = Expense.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_expenses += PayrollRun.objects.aggregate(total=Sum("total_gross"))["total"] or Decimal("0")
    cogs = SalesOrderItem.objects.aggregate(total=Sum(F("quantity") * F("unit_cost")))["total"] or Decimal("0")
    monthly_labels, monthly_sales, monthly_expenses = [], [], []
    today = timezone.localdate()
    for offset in range(-11, 1):
        start = _shift_month(_month_start(today.year, today.month), offset)
        end = _shift_month(start, 1)
        monthly_labels.append(start.strftime("%b %y"))
        monthly_sales.append(float(SalesOrder.objects.exclude(status="CANCELLED").filter(created_at__date__gte=start, created_at__date__lt=end).aggregate(total=Sum("subtotal"))["total"] or 0))
        expense_total = Expense.objects.filter(expense_date__gte=start, expense_date__lt=end).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        payroll_total = PayrollRun.objects.filter(period=start.strftime("%Y-%m")).aggregate(total=Sum("total_gross"))["total"] or Decimal("0")
        monthly_expenses.append(float(expense_total + payroll_total))
    categories = list(Product.objects.values("category").annotate(quantity=Sum("salesorderitem__quantity")).order_by("category"))
    return render(request, "erp/reports.html", {"page_title": "Business intelligence", "total_sales": total_sales,
        "total_expenses": total_expenses, "net_proxy": total_sales - total_expenses,
        "chart_data": json.dumps({"labels": monthly_labels, "sales": monthly_sales, "expenses": monthly_expenses,
             "categoryLabels": [x["category"].title() for x in categories], "categoryValues": [float(x["quantity"] or 0) for x in categories]}),
        "low_stock": [p for p in Product.objects.all() if p.stock_status in {"LOW", "OUT"}]})

@login_required
def audit_logs(request):
    qs = AuditLog.objects.select_related("actor").all()[:250]
    records = [{"primary": x.action, "secondary": f"{x.entity} · {x.entity_id}", "cells": [x.description, x.actor.username if x.actor else "System", x.created_at.strftime("%d %b %Y %H:%M"), x.ip_address or "—"], "tag": x.action.title(), "tag_class": "info"} for x in qs]
    return _render_table(request, title="Audit trail", eyebrow="GOVERNANCE", description="Trace who performed important actions and when they occurred.", add_url="", headers=["Description", "Actor", "Timestamp", "IP address"], records=records, icon="◷")

@staff_required
def company_settings(request):
    company = Company.objects.order_by("id").first()
    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            obj = form.save()
            audit(request.user, "UPDATE", "Company", obj.pk, f"Updated company profile", request)
            messages.success(request, "Company profile saved.")
            return redirect("company-settings")
    else:
        form = CompanyForm(instance=company)
    return render(request, "erp/form.html", {"page_title": "Company settings", "eyebrow": "CONFIGURATION", "description": "Configure your legal and contact identity.", "form": form, "cancel_url": reverse("dashboard"), "submit_label": "Save company profile"})


def _save_model_form(request, form_class, title, eyebrow, description, success_text, entity):
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            obj = form.save()
            audit(request.user, "CREATE", entity, obj.pk, success_text, request)
            messages.success(request, success_text)
            return redirect({"Customer": "customers", "Supplier": "suppliers", "Product": "products", "Employee": "employees", "BankAccount": "finance"}[entity])
    else:
        form = form_class()
    cancel = {"Customer": "customers", "Supplier": "suppliers", "Product": "products", "Employee": "employees", "BankAccount": "finance"}[entity]
    return render(request, "erp/form.html", {"page_title": title, "eyebrow": eyebrow, "description": description, "form": form, "cancel_url": reverse(cancel), "submit_label": "Save record"})

@staff_required
def customer_create(request):
    return _save_model_form(request, CustomerForm, "Add customer", "CRM", "Create a customer profile.", "Customer created successfully.", "Customer")

@staff_required
def supplier_create(request):
    return _save_model_form(request, SupplierForm, "Add supplier", "PROCUREMENT", "Create a supplier profile.", "Supplier created successfully.", "Supplier")

@staff_required
def product_create(request):
    return _save_model_form(request, ProductForm, "Add product", "INVENTORY", "Add an item to the product catalogue. Opening stock is recorded separately through purchases.", "Product created successfully.", "Product")

@staff_required
def employee_create(request):
    return _save_model_form(request, EmployeeForm, "Add employee", "HUMAN RESOURCES", "Create an employee record.", "Employee created successfully.", "Employee")

@staff_required
def bank_create(request):
    form = BankAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        bank = form.save()
        if bank.opening_balance > 0:
            from .services import make_reference, post_journal
            post_journal(make_reference("JE"), f"Opening bank balance · {bank.name}", [
                ("1010", "Bank", "ASSET", bank.opening_balance, 0, "Opening bank balance"),
                ("3000", "Owner Equity", "EQUITY", 0, bank.opening_balance, "Opening balance equity"),
            ], actor=request.user, source_type="BANK_ACCOUNT", source_id=bank.pk)
        audit(request.user, "CREATE", "BankAccount", bank.pk, f"Created bank account {bank.name}", request)
        messages.success(request, "Bank account created successfully.")
        return redirect("finance")
    return render(request, "erp/form.html", {"page_title": "Add bank account", "eyebrow": "FINANCE", "description": "Register a company bank or cash account. An opening balance is also posted to the ledger.", "form": form, "cancel_url": reverse("finance"), "submit_label": "Save bank account"})

@staff_required
def customer_edit(request, pk):
    return _edit_model_form(request, Customer, CustomerForm, pk, "Edit customer", "CRM", "customers", "Customer")

@staff_required
def supplier_edit(request, pk):
    return _edit_model_form(request, Supplier, SupplierForm, pk, "Edit supplier", "PROCUREMENT", "suppliers", "Supplier")

@staff_required
def product_edit(request, pk):
    return _edit_model_form(request, Product, ProductForm, pk, "Edit product", "INVENTORY", "products", "Product")

@staff_required
def employee_edit(request, pk):
    return _edit_model_form(request, Employee, EmployeeForm, pk, "Edit employee", "HUMAN RESOURCES", "employees", "Employee")

def _edit_model_form(request, model, form_class, pk, title, eyebrow, cancel_name, entity):
    obj = get_object_or_404(model, pk=pk)
    if request.method == "POST":
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            saved = form.save()
            audit(request.user, "UPDATE", entity, saved.pk, f"Updated {entity.lower()} record", request)
            messages.success(request, f"{entity} updated successfully.")
            return redirect(cancel_name)
    else:
        form = form_class(instance=obj)
    return render(request, "erp/form.html", {"page_title": title, "eyebrow": eyebrow, "description": "Update this record. Deactivate records instead of deleting business history.", "form": form, "cancel_url": reverse(cancel_name), "submit_label": "Save changes"})

@staff_required
def sale_create(request):
    form = SalesForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            order, invoice = create_sale(customer=form.cleaned_data["customer"], product=form.cleaned_data["product"],
                warehouse=form.cleaned_data["warehouse"], quantity=form.cleaned_data["quantity"],
                unit_price=form.cleaned_data["unit_price"], tax_rate=form.cleaned_data["tax_rate"],
                actor=request.user, request=request)
            if form.cleaned_data.get("notes"):
                order.notes = form.cleaned_data["notes"]
                order.save(update_fields=["notes", "updated_at"])
            messages.success(request, f"Sale {order.number} created and invoice {invoice.number} issued. Stock and ledger updated.")
            return redirect("sales")
        except (ValidationError, Product.DoesNotExist) as exc:
            form.add_error(None, exc.message if hasattr(exc, "message") else str(exc))
    return render(request, "erp/form.html", {"page_title": "Create sales order", "eyebrow": "REVENUE CYCLE", "description": "This workflow checks stock, creates an invoice, and posts balanced ledger entries atomically.", "form": form, "cancel_url": reverse("sales"), "submit_label": "Confirm sale"})

@staff_required
def purchase_create(request):
    form = PurchaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            order, invoice = create_purchase(supplier=form.cleaned_data["supplier"], product=form.cleaned_data["product"],
                warehouse=form.cleaned_data["warehouse"], quantity=form.cleaned_data["quantity"],
                unit_cost=form.cleaned_data["unit_cost"], tax_rate=form.cleaned_data["tax_rate"],
                actor=request.user, request=request)
            if form.cleaned_data.get("notes"):
                order.notes = form.cleaned_data["notes"]
                order.save(update_fields=["notes", "updated_at"])
            messages.success(request, f"Purchase {order.number} received. Stock and supplier payable updated.")
            return redirect("purchases")
        except ValidationError as exc:
            form.add_error(None, exc.message if hasattr(exc, "message") else str(exc))
    return render(request, "erp/form.html", {"page_title": "Receive purchase", "eyebrow": "PROCUREMENT", "description": "Record goods received, increase stock and post the supplier payable.", "form": form, "cancel_url": reverse("purchases"), "submit_label": "Receive purchase"})

@staff_required
def expense_create(request):
    form = ExpenseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            expense = create_expense(category=form.cleaned_data["category"], description=form.cleaned_data["description"],
                amount=form.cleaned_data["amount"], bank_account=form.cleaned_data["bank_account"],
                expense_date=form.cleaned_data.get("expense_date"), actor=request.user, request=request)
            messages.success(request, f"Expense {expense.reference} recorded with bank and ledger entries.")
            return redirect("expenses")
        except ValidationError as exc:
            form.add_error(None, exc.message if hasattr(exc, "message") else str(exc))
    return render(request, "erp/form.html", {"page_title": "Record expense", "eyebrow": "COST CONTROL", "description": "Record a paid expense and update bank balances and the general ledger.", "form": form, "cancel_url": reverse("expenses"), "submit_label": "Record expense"})

@staff_required
def payment_create(request):
    form = PaymentForm(request.POST or None)
    invoice_id = request.GET.get("invoice") or request.POST.get("invoice")
    if invoice_id and not request.method == "POST":
        form.fields["invoice"].initial = invoice_id
    if request.method == "POST" and form.is_valid():
        try:
            payment = record_payment(invoice=form.cleaned_data["invoice"], bank_account=form.cleaned_data["bank_account"],
                amount=form.cleaned_data["amount"], reference=form.cleaned_data["reference"], actor=request.user, request=request)
            messages.success(request, f"Payment {payment.reference} recorded successfully.")
            return redirect("invoices")
        except ValidationError as exc:
            form.add_error(None, exc.message if hasattr(exc, "message") else str(exc))
    return render(request, "erp/form.html", {"page_title": "Record payment", "eyebrow": "ACCOUNTS RECEIVABLE / PAYABLE", "description": "Record a partial or full customer receipt or supplier payment.", "form": form, "cancel_url": reverse("invoices"), "submit_label": "Record payment"})

@staff_required
def payroll_create(request):
    form = PayrollForm(request.POST or None, initial={"period": timezone.localdate().strftime("%Y-%m")})
    if request.method == "POST" and form.is_valid():
        try:
            run = create_payroll_run(period=form.cleaned_data["period"], actor=request.user, request=request)
            messages.success(request, f"Payroll run for {run.period} created with {run.payslips.count()} payslips.")
            return redirect("payroll")
        except ValidationError as exc:
            form.add_error(None, exc.message if hasattr(exc, "message") else str(exc))
    runs = PayrollRun.objects.prefetch_related("payslips__employee").all()[:24]
    return render(request, "erp/payroll.html", {"page_title": "Payroll management", "form": form, "runs": runs, "employees_count": Employee.objects.filter(status="ACTIVE").count()})

@login_required
def export_data(request, dataset):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="enterprise360-{dataset}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    def safe(value):
        text = str(value if value is not None else "")
        return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text
    if dataset == "customers":
        writer.writerow(["Code", "Name", "Email", "Phone", "City", "Status"])
        for x in Customer.objects.all(): writer.writerow([safe(v) for v in [x.customer_code, x.name, x.email, x.phone, x.city, x.status]])
    elif dataset == "suppliers":
        writer.writerow(["Code", "Name", "Contact", "Email", "Phone", "City"])
        for x in Supplier.objects.all(): writer.writerow([safe(v) for v in [x.supplier_code, x.name, x.contact_name, x.email, x.phone, x.city]])
    elif dataset == "products":
        writer.writerow(["SKU", "Name", "Category", "Cost", "Sale price", "Stock"])
        for x in Product.objects.all(): writer.writerow([safe(v) for v in [x.sku, x.name, x.category, x.cost_price, x.sale_price, x.stock_quantity]])
    elif dataset == "sales":
        writer.writerow(["Order", "Customer", "Date", "Subtotal", "Tax", "Total", "Status"])
        for x in SalesOrder.objects.select_related("customer"): writer.writerow([safe(v) for v in [x.number, x.customer.name, x.created_at.date(), x.subtotal, x.tax_amount, x.total, x.status]])
    elif dataset == "purchases":
        writer.writerow(["Order", "Supplier", "Date", "Subtotal", "Tax", "Total", "Status"])
        for x in PurchaseOrder.objects.select_related("supplier"): writer.writerow([safe(v) for v in [x.number, x.supplier.name, x.created_at.date(), x.subtotal, x.tax_amount, x.total, x.status]])
    elif dataset == "expenses":
        writer.writerow(["Reference", "Category", "Description", "Date", "Amount"])
        for x in Expense.objects.all(): writer.writerow([safe(v) for v in [x.reference, x.category, x.description, x.expense_date, x.amount]])
    else:
        return HttpResponse("Unknown export", status=404)
    return response
