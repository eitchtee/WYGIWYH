from django.db.models import Case, F, When


def shown_exchange_currency(path):
    """Query expression for the exchange currency id at ``path`` (an account or a
    currency lookup, such as ``"account__currency__"``), or NULL when that object
    hides its exchanged amounts."""
    return Case(
        When(
            **{f"{path}show_exchanged_amounts": True},
            then=F(f"{path}exchange_currency"),
        )
    )
