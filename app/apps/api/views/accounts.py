from rest_framework import viewsets

from apps.api.custom.pagination import CustomPageNumberPagination
from apps.accounts.models import AccountGroup, Account
from apps.api.serializers import AccountGroupSerializer, AccountSerializer


class AccountGroupViewSet(viewsets.ModelViewSet):
    queryset = AccountGroup.objects.all()
    serializer_class = AccountGroupSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return AccountGroup.objects.all().order_by("id")


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return (
            Account.objects.all()
            .order_by("id")
            .select_related("group", "currency", "exchange_currency")
        )
