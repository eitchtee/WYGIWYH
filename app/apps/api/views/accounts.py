from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import AccountGroup, Account
from apps.accounts.services import get_account_balance
from apps.api.serializers import (
    AccountGroupSerializer,
    AccountSerializer,
    AccountBalanceSerializer,
)


class AccountGroupViewSet(viewsets.ModelViewSet):
    """ViewSet for managing account groups."""

    queryset = AccountGroup.objects.all()
    serializer_class = AccountGroupSerializer
    filterset_fields = {
        "name": ["exact", "icontains"],
        "owner": ["exact"],
    }
    search_fields = ["name"]
    ordering_fields = "__all__"
    ordering = ["id"]

    def get_queryset(self):
        return AccountGroup.objects.all()


@extend_schema_view(
    balance=extend_schema(
        summary="Get account balance",
        description="Returns the current and projected balance for the account, along with currency data.",
        responses={200: AccountBalanceSerializer},
    ),
)
class AccountViewSet(viewsets.ModelViewSet):
    """ViewSet for managing accounts."""

    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    filterset_fields = {
        "name": ["exact", "icontains"],
        "group": ["exact", "isnull"],
        "currency": ["exact"],
        "exchange_currency": ["exact", "isnull"],
        "is_asset": ["exact"],
        "is_archived": ["exact"],
        "owner": ["exact"],
    }
    search_fields = ["name"]
    ordering_fields = "__all__"
    ordering = ["id"]

    def get_queryset(self):
        return Account.objects.all().select_related(
            "group", "currency", "exchange_currency"
        )

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def balance(self, request, pk=None):
        """Get current and projected balance for an account."""
        account = self.get_object()

        current_balance = get_account_balance(account, paid_only=True)
        projected_balance = get_account_balance(account, paid_only=False)

        serializer = AccountBalanceSerializer(
            {
                "current_balance": current_balance,
                "projected_balance": projected_balance,
                "currency": account.currency,
            }
        )

        return Response(serializer.data)
