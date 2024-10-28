from django.db.models import Case, When, Value, IntegerField, QuerySet
from django.utils import timezone


def default_order(queryset: QuerySet, extra_ordering=None) -> QuerySet:
    if extra_ordering is None:
        extra_ordering = list()

    today = timezone.localdate(timezone.now())
    yesterday = today - timezone.timedelta(days=1)
    tomorrow = today + timezone.timedelta(days=1)
    last_7_days = today - timezone.timedelta(days=7)
    next_7_days = today + timezone.timedelta(days=7)

    return queryset.annotate(
        date_order=Case(
            When(date=today, then=Value(0)),
            When(date=tomorrow, then=Value(1)),
            When(date=yesterday, then=Value(2)),
            When(date__lte=next_7_days, date__gte=tomorrow, then=Value(3)),
            When(date__gte=last_7_days, date__lte=today, then=Value(4)),
            default=Value(5),
            output_field=IntegerField(),
        )
    ).order_by("date_order", *extra_ordering)
