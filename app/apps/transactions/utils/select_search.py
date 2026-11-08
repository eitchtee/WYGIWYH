import datetime
import re
from decimal import Decimal, InvalidOperation

from apps.common.functions.format import get_format
from apps.common.utils.django import django_to_python_datetime
from apps.transactions.templatetags.currency_display import currency_display
from django.db.models import Q
from django.template.defaultfilters import date as date_filter


def transaction_option(t):
    """Data used by the transaction picker (tom-select) to render a mini transaction."""
    currency = t.account.currency
    return {
        "value": str(t.id),
        "text": str(t),
        "description": t.description,
        "date": date_filter(t.date, "SHORT_DATE_FORMAT"),
        "type": t.type,
        "is_paid": t.is_paid,
        "amount": currency_display(
            t.amount,
            currency.prefix,
            currency.suffix,
            currency.decimal_places,
            string=True,
        ),
        "account": (
            f"{t.account.group.name} • {t.account.name}"
            if t.account.group
            else t.account.name
        ),
        "category": t.category.name if t.category else "",
        "tags": [tag.name for tag in t.tags.all()],
        "entities": [entity.name for entity in t.entities.all()],
    }


def _parse_date(term):
    """Match a term against the user's date format; without a year it matches any year."""
    fmt = django_to_python_datetime(get_format("SHORT_DATE_FORMAT"))
    try:
        return Q(date=datetime.datetime.strptime(term, fmt).date())
    except ValueError:
        pass
    # Drop the year and its adjacent separator, e.g. "%d/%m/%Y" -> "%d/%m"
    no_year = re.sub(r"[^%\w]?%[Yy][^%\w]?", "", fmt, count=1).strip()
    if no_year == fmt or not no_year:
        return None
    try:
        # 2000 is a leap year, so 29/02 parses
        parsed = datetime.datetime.strptime(f"{term} 2000", f"{no_year} %Y")
    except ValueError:
        return None
    return Q(date__day=parsed.day, date__month=parsed.month)


def _parse_amount(term):
    if not re.fullmatch(r"[\d.,\s]*\d[\d.,\s]*", term):
        return None
    thousand = get_format("THOUSAND_SEPARATOR")
    decimal = get_format("DECIMAL_SEPARATOR")
    normalized = term.replace(thousand, "").replace(decimal, ".")
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    if decimal not in term:
        # Whole number: "12" finds 12.00 to 12.99
        return Q(amount__gte=value, amount__lt=value + 1)
    return Q(amount=value)


def search_transactions(queryset, search_term):
    """Every word must match some field (description, category, entity, date, amount...)."""
    matches = queryset.model.objects.all()
    for term in search_term.split():
        term_q = (
            Q(description__icontains=term)
            | Q(notes__icontains=term)
            | Q(internal_note__icontains=term)
            | Q(tags__name__icontains=term)
            | Q(entities__name__icontains=term)
            | Q(category__name__icontains=term)
            | Q(account__name__icontains=term)
            | Q(account__group__name__icontains=term)
        )
        for extra in (_parse_date(term), _parse_amount(term)):
            if extra is not None:
                term_q |= extra
        # One filter() per word so different words can match different tags/entities
        matches = matches.filter(term_q)
    # id__in avoids duplicate rows from the tag/entity joins
    return queryset.filter(id__in=matches.values("id"))
