import os
from datetime import date
from decimal import Decimal

import requests
from django import forms
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.bank_sync.providers.base import (
    BankSyncProvider,
    RemoteAccount,
    RemoteTransaction,
)

DEFAULT_BASE_URL = "https://www.lunchflow.app/api/v1"


class LunchFlowProvider(BankSyncProvider):
    """https://www.lunchflow.app/docs/api/personal-api-overview"""

    settings_fields = {
        "api_key": forms.CharField(
            label=gettext_lazy("API Key"),
            # Not a PasswordInput: browsers autofill those with saved logins
            widget=forms.TextInput(attrs={"autocomplete": "off"}),
            help_text=gettext_lazy(
                "Create a REST API destination on Lunch Flow and give it access to "
                "the accounts you want to sync."
            ),
        ),
    }

    def __init__(self, settings: dict):
        super().__init__(settings)
        # Server side only, users must not point the server at arbitrary hosts
        self.base_url = os.getenv("LUNCHFLOW_API_URL", DEFAULT_BASE_URL).rstrip("/")
        self.session = requests.Session()
        self.session.headers["x-api-key"] = self.settings.get("api_key", "")

    def _get(self, path: str, **params) -> dict:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _balance_currency(self, account_id) -> str:
        # The account list has no currency, the balance does
        try:
            return self._get(f"/accounts/{account_id}/balance")["balance"]["currency"]
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return ""

    def list_accounts(self) -> list[RemoteAccount]:
        accounts = []
        for account in self._get("/accounts")["accounts"]:
            currency = account.get("currency") or self._balance_currency(account["id"])
            status = account.get("status") or "ACTIVE"
            accounts.append(
                RemoteAccount(
                    id=str(account["id"]),
                    name=" - ".join(
                        filter(None, [account.get("institution_name"), account["name"]])
                    ),
                    currencies=(currency.upper(),) if currency else (),
                    error=(
                        ""
                        if status == "ACTIVE"
                        else _(
                            "Lunch Flow reports this account as %(status)s, "
                            "check the connection on Lunch Flow."
                        )
                        % {"status": status}
                    ),
                )
            )
        return accounts

    def get_transactions(
        self, account_id: str, start_date: date
    ) -> list[RemoteTransaction]:
        data = self._get(
            f"/accounts/{account_id}/transactions", **{"from": start_date.isoformat()}
        )
        transactions = []
        for tx in data["transactions"]:
            # Pending ones are excluded by default, but they change ids when posted
            if tx.get("isPending"):
                continue
            merchant = (tx.get("merchant") or "").strip()
            description = (tx.get("description") or "").strip()
            transactions.append(
                RemoteTransaction(
                    id=str(tx["id"]),
                    date=date.fromisoformat(tx["date"][:10]),
                    amount=Decimal(str(tx["amount"])),
                    description=merchant or description,
                    notes=description if merchant and description != merchant else "",
                    currency=(tx.get("currency") or "").upper(),
                )
            )
        return transactions
