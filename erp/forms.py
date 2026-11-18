from django import forms
from .models import BankAccount, Company, Customer, Employee, Expense, Product, Supplier, Warehouse, Department, Invoice

WIDGET_CLASS = "form-control"

class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs["class"] = "form-check-input"
            else:
                field.widget.attrs["class"] = WIDGET_CLASS

class CustomerForm(StyledModelForm):
    class Meta:
        model = Customer
        fields = ["customer_code", "name", "email", "phone", "city", "address", "tax_number", "credit_limit", "status"]

class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = ["supplier_code", "name", "contact_name", "email", "phone", "city", "address", "tax_number", "status"]

class ProductForm(StyledModelForm):
    class Meta:
        model = Product
        fields = ["sku", "name", "category", "description", "cost_price", "sale_price", "reorder_level", "active"]

class EmployeeForm(StyledModelForm):
    class Meta:
        model = Employee
        fields = ["employee_code", "first_name", "last_name", "email", "phone", "department", "job_title", "hire_date", "monthly_salary", "status"]
        widgets = {"hire_date": forms.DateInput(attrs={"type": "date"})}

class BankAccountForm(StyledModelForm):
    class Meta:
        model = BankAccount
        fields = ["name", "bank_name", "account_number_masked", "currency", "opening_balance", "active"]

class CompanyForm(StyledModelForm):
    class Meta:
        model = Company
        fields = ["name", "legal_name", "email", "phone", "address", "tax_number", "currency"]

class SalesForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.filter(status="ACTIVE"), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    product = forms.ModelChoiceField(queryset=Product.objects.filter(active=True), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.filter(active=True), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    quantity = forms.DecimalField(min_value=0.01, decimal_places=2, max_digits=12, widget=forms.NumberInput(attrs={"class": WIDGET_CLASS, "step": "0.01"}))
    unit_price = forms.DecimalField(min_value=0, decimal_places=2, max_digits=12, widget=forms.NumberInput(attrs={"class": WIDGET_CLASS, "step": "0.01"}))
    tax_rate = forms.DecimalField(min_value=0, max_value=100, initial=20, decimal_places=2, widget=forms.NumberInput(attrs={"class": WIDGET_CLASS, "step": "0.01"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": WIDGET_CLASS, "rows": 2}))

class PurchaseForm(forms.Form):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.filter(status="ACTIVE"), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    product = forms.ModelChoiceField(queryset=Product.objects.filter(active=True), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.filter(active=True), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    quantity = forms.DecimalField(min_value=0.01, decimal_places=2, max_digits=12, widget=forms.NumberInput(attrs={"class": WIDGET_CLASS, "step": "0.01"}))
    unit_cost = forms.DecimalField(min_value=0, decimal_places=2, max_digits=12, widget=forms.NumberInput(attrs={"class": WIDGET_CLASS, "step": "0.01"}))
    tax_rate = forms.DecimalField(min_value=0, max_value=100, initial=20, decimal_places=2, widget=forms.NumberInput(attrs={"class": WIDGET_CLASS, "step": "0.01"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": WIDGET_CLASS, "rows": 2}))

class ExpenseForm(forms.Form):
    category = forms.ChoiceField(choices=Expense.CATEGORY_CHOICES, widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    description = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"class": WIDGET_CLASS}))
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, max_digits=14, widget=forms.NumberInput(attrs={"class": WIDGET_CLASS, "step": "0.01"}))
    bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.filter(active=True), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    expense_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": WIDGET_CLASS, "type": "date"}))

class PaymentForm(forms.Form):
    invoice = forms.ModelChoiceField(queryset=Invoice.objects.all(), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.filter(active=True), widget=forms.Select(attrs={"class": WIDGET_CLASS}))
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, max_digits=14, widget=forms.NumberInput(attrs={"class": WIDGET_CLASS, "step": "0.01"}))
    reference = forms.CharField(required=False, max_length=80, widget=forms.TextInput(attrs={"class": WIDGET_CLASS}))

class PayrollForm(forms.Form):
    period = forms.RegexField(regex=r"^\d{4}-(0[1-9]|1[0-2])$", max_length=7,
        error_messages={"invalid": "Use YYYY-MM format, for example 2026-11."},
        widget=forms.TextInput(attrs={"class": WIDGET_CLASS, "placeholder": "YYYY-MM"}))
