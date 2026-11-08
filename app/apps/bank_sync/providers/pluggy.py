import re
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import requests
from django import forms
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.bank_sync.providers.base import (
    BankSyncProvider,
    RemoteAccount,
    RemoteTransaction,
)

BASE_URL = "https://api.pluggy.ai"
# Item statuses that need the user to reconnect on Pluggy
NEEDS_ACTION = {"LOGIN_ERROR", "WAITING_USER_INPUT"}


class PluggyProvider(BankSyncProvider):
    """https://docs.pluggy.ai"""

    settings_fields = {
        "client_id": forms.CharField(
            label=gettext_lazy("Client ID"),
            widget=forms.TextInput(attrs={"autocomplete": "off"}),
        ),
        "client_secret": forms.CharField(
            label=gettext_lazy("Client Secret"),
            # Not a PasswordInput: browsers autofill those with saved logins
            widget=forms.TextInput(attrs={"autocomplete": "off"}),
        ),
        "item_ids": forms.CharField(
            label=gettext_lazy("Item IDs"),
            widget=forms.TextInput(attrs={"autocomplete": "off"}),
            help_text=gettext_lazy(
                "The IDs of your Pluggy connections (items), separated by commas. "
                "Meu Pluggy shows them for each connected institution."
            ),
        ),
    }

    def __init__(self, settings: dict):
        super().__init__(settings)
        self.session = requests.Session()
        self.item_ids = [
            item_id
            for item_id in re.split(r"[\s,]+", self.settings.get("item_ids", ""))
            if item_id
        ]

    def _get(self, path: str, **params) -> dict:
        if "X-API-KEY" not in self.session.headers:
            # Lasts 2 hours, longer than any sync
            response = self.session.post(
                f"{BASE_URL}/auth",
                json={
                    "clientId": self.settings.get("client_id", ""),
                    "clientSecret": self.settings.get("client_secret", ""),
                },
                timeout=30,
            )
            response.raise_for_status()
            self.session.headers["X-API-KEY"] = response.json()["apiKey"]
        response = self.session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def list_accounts(self) -> list[RemoteAccount]:
        accounts = []
        for item_id in self.item_ids:
            item = self._get(f"/items/{item_id}")
            institution = (item.get("connector") or {}).get("name")
            status = item.get("status") or ""
            error = (
                _(
                    "Pluggy reports this connection as %(status)s, reconnect it "
                    "on Pluggy."
                )
                % {"status": status}
                if status in NEEDS_ACTION
                else ""
            )
            for account in self._get("/accounts", itemId=item_id)["results"]:
                currency = account.get("currencyCode") or ""
                accounts.append(
                    RemoteAccount(
                        id=str(account["id"]),
                        name=" - ".join(
                            filter(
                                None,
                                [
                                    institution,
                                    account.get("marketingName") or account["name"],
                                    account.get("number"),
                                ],
                            )
                        ),
                        currencies=(currency.upper(),) if currency else (),
                        error=error,
                    )
                )
        return accounts

    def get_transactions(
        self, account_id: str, start_date: date
    ) -> list[RemoteTransaction]:
        params = {"accountId": account_id, "dateFrom": start_date.isoformat()}
        transactions = []
        while True:
            data = self._get("/v2/transactions", **params)
            for tx in data["results"]:
                day = date.fromisoformat(tx["date"][:10])
                # Pending keeps its id once it posts (a card's open bill). Future
                # ones (installments, scheduled payments) wait for their date
                pending = tx.get("status") == "PENDING"
                if pending and day > timezone.localdate():
                    continue
                converted = tx.get("amountInAccountCurrency")
                amount = abs(Decimal(str(tx["amount"] if converted is None else converted)))
                notes = ""
                if converted is not None:
                    # Foreign purchase: keep the account's amount, note the original
                    notes = f"{tx.get('currencyCode', '')} {abs(Decimal(str(tx['amount'])))}"
                transactions.append(
                    RemoteTransaction(
                        id=str(tx["id"]),
                        # Installments already come dated in their own month
                        date=day,
                        # Not the amount's sign: cards keep theirs, purchases are
                        # positive. `type` is normalized for every account
                        amount=amount if tx.get("type") == "CREDIT" else -amount,
                        description=(tx.get("description") or "").strip(),
                        notes=notes,
                        currency=""
                        if converted is not None
                        else (tx.get("currencyCode") or "").upper(),
                        pending=pending,
                    )
                )
            if not data.get("next"):
                return transactions
            # Send our own filters again with the cursor, `next` may drop them
            params["after"] = parse_qs(urlsplit(data["next"]).query)["after"][0]
