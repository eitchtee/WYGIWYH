from rest_framework import viewsets
from apps.accounts.models import AccountGroup, Account
from apps.api.serializers import AccountGroupSerializer, AccountSerializer


class AccountGroupViewSet(viewsets.ModelViewSet):
    queryset = AccountGroup.objects.all()
    serializer_class = AccountGroupSerializer


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related("group", "currency", "exchange_currency")
