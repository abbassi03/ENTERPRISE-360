from django.contrib import admin
from .models import (
    Account, AuditLog, BankAccount, BankTransaction, Company, Customer, Department,
    Employee, Expense, Invoice, JournalEntry, JournalLine, PayrollRun, Payslip,
    Product, PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    StockMovement, Supplier, Warehouse, Payment,
)

class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("reference", "entry_date", "description", "posted")
    search_fields = ("reference", "description")
    inlines = [JournalLineInline]
    readonly_fields = ("created_at", "updated_at")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "cost_price", "sale_price", "active")
    list_filter = ("category", "active")
    search_fields = ("sku", "name")

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "invoice_type", "issue_date", "due_date", "total", "status")
    list_filter = ("invoice_type", "status")
    search_fields = ("number",)

admin.site.register([
    Account, AuditLog, BankAccount, BankTransaction, Company, Customer, Department,
    Employee, Expense, PayrollRun, Payslip, PurchaseOrder, PurchaseOrderItem,
    SalesOrder, SalesOrderItem, StockMovement, Supplier, Warehouse, Payment,
])
