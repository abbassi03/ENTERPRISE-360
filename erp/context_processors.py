from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from .models import Company

def enterprise_context(request):
    try:
        company = Company.objects.order_by("id").first()
    except (OperationalError, ProgrammingError):
        company = None
    return {
        "enterprise_company": company,
        "currency_code": settings.CURRENCY_CODE,
        "company_name": company.name if company else settings.COMPANY_NAME,
    }
