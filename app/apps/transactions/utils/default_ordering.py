from typing import Optional, Literal

from django.db.models import Case, When, Value, IntegerField, QuerySet
from django.utils import timezone


def default_order(
    queryset: QuerySet,
    order: Literal["default", "newer", "older"],
    extra_ordering: Optional[list] = None,
) -> QuerySet:
    if extra_ordering is None:
        extra_ordering = list()

    available_orders = {
        "default": ["date_order", "date", "id"],
        "newer": ["-date", "id"],
        "older": ["date", "id"],
    }

    today = timezone.localdate(timezone.now())
    yesterday = today - timezone.timedelta(days=1)
    tomorrow = today + timezone.timedelta(days=1)

    return queryset.annotate(
        date_order=Case(
            When(date=today, then=Value(0)),
            When(date=tomorrow, then=Value(1)),
            When(date=yesterday, then=Value(2)),
            When(date__gt=tomorrow, then=Value(3)),
            When(date__lt=yesterday, then=Value(4)),
            default=Value(5),
            output_field=IntegerField(),
        )
    ).order_by(*available_orders.get(order, list()), *extra_ordering)
