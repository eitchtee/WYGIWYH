from apps.transactions.templatetags.currency_display import currency_display
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
