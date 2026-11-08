import base64
import binascii
import os
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import unquote, urlsplit, urlunsplit

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

DEFAULT_ALLOWED_HOSTS = "bridge.simplefin.org,beta-bridge.simplefin.org"
# SimpleFIN Bridge refuses longer ranges in a single request
MAX_RANGE_DAYS = 90


def _check_host(url: str) -> None:
    # Tokens are user input: without this they could point the server at any host
    allowed = {
        host.strip().lower()
        for host in os.getenv("SIMPLEFIN_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS).split(",")
        if host.strip()
    }
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or (parts.hostname or "") not in allowed:
        raise ValueError(
            _("SimpleFIN server %(host)s isn't allowed on this instance.")
            % {"host": parts.hostname or url}
        )


def _timestamp(day: date) -> int:
    # Local midnight, so windows and transaction dates agree on what a day is
    return int(
        datetime.combine(day, time(), tzinfo=timezone.get_current_timezone()).timestamp()
    )


class SimpleFINProvider(BankSyncProvider):
    """https://www.simplefin.org/protocol.html"""

    # SimpleFIN Bridge disables tokens that go much past ~24 requests a day, and a
    # sync costs one plus one per account
    min_sync_interval = 6

    settings_fields = {
        "access_url": forms.CharField(
            label=gettext_lazy("Setup Token"),
            widget=forms.TextInput(attrs={"autocomplete": "off"}),
            help_text=gettext_lazy(
                "Paste a setup token from your SimpleFIN server. It can only be "
                "used once: on save it's exchanged for an access URL, which is "
                "what you'll see here afterwards."
            ),
        ),
    }

    @classmethod
    def clean_settings(cls, settings: dict) -> dict:
        try:
            return cls._claim(settings)
        except ValueError as e:
            raise forms.ValidationError(str(e))

    @staticmethod
    def _claim(settings: dict) -> dict:
        value = settings["access_url"].strip()
        # Already claimed: the form is being saved again
        if not value.startswith(("http://", "https://")):
            try:
                claim_url = base64.b64decode(
                    value + "=" * (-len(value) % 4), validate=True
                ).decode()
            except (binascii.Error, UnicodeDecodeError):
                raise ValueError(_("This isn't a valid SimpleFIN setup token."))
            _check_host(claim_url)
            try:
                response = requests.post(claim_url, timeout=30)
                response.raise_for_status()
            except requests.RequestException as e:
                raise ValueError(
                    _(
                        "Couldn't claim the setup token, it may have been used "
                        "already: %(error)s"
                    )
                    % {"error": e}
                )
            value = response.text.strip()
        _check_host(value)
        return {**settings, "access_url": value}

    def __init__(self, settings: dict):
        super().__init__(settings)
        parts = urlsplit(self.settings.get("access_url", ""))
        self.session = requests.Session()
        # Credentials go in a header, not the URL, so errors never show them
        self.session.auth = (unquote(parts.username or ""), unquote(parts.password or ""))
        netloc = (parts.hostname or "") + (f":{parts.port}" if parts.port else "")
        self.base_url = urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))

    def _get_accounts(self, **params) -> dict:
        # Settings can also arrive through a backup restore, skipping the form
        _check_host(self.base_url)
        response = self.session.get(
            f"{self.base_url}/accounts",
            params={"version": "2", **params},
            # Slow: the server can fetch from every bank on each request
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def list_accounts(self) -> list[RemoteAccount]:
        data = self._get_accounts(**{"balances-only": "1"})
        connections = {c["conn_id"]: c.get("name", "") for c in data.get("connections", [])}
        account_errors, connection_errors = {}, {}
        for error in data.get("errlist", []):
            if error.get("account_id"):
                account_errors.setdefault(error["account_id"], error.get("msg", ""))
            elif error.get("conn_id"):
                connection_errors.setdefault(error["conn_id"], error.get("msg", ""))

        accounts = []
        for account in data["accounts"]:
            institution = connections.get(account.get("conn_id")) or (
                account.get("org") or {}
            ).get("name")
            currency = account.get("currency") or ""
            accounts.append(
                RemoteAccount(
                    id=str(account["id"]),
                    name=" - ".join(filter(None, [institution, account["name"]])),
                    # Custom currencies are URLs, nothing to match them against
                    currencies=(currency.upper(),) if currency and "/" not in currency else (),
                    error=account_errors.get(account["id"])
                    or connection_errors.get(account.get("conn_id"), ""),
                )
            )
        return accounts

    def get_transactions(
        self, account_id: str, start_date: date
    ) -> list[RemoteTransaction]:
        transactions = []
        start, stop = start_date, timezone.localdate() + timedelta(days=1)
        while start < stop:
            end = min(start + timedelta(days=MAX_RANGE_DAYS), stop)
            data = self._get_accounts(
                account=account_id,
                **{"start-date": _timestamp(start), "end-date": _timestamp(end)},
            )
            for account in data["accounts"]:
                if str(account["id"]) != account_id:
                    continue
                currency = account.get("currency") or ""
                for tx in account.get("transactions", []):
                    if tx.get("pending"):
                        continue
                    payee = (tx.get("payee") or "").strip()
                    description = (tx.get("description") or "").strip()
                    transactions.append(
                        RemoteTransaction(
                            id=str(tx["id"]),
                            date=datetime.fromtimestamp(
                                tx["posted"], tz=timezone.get_current_timezone()
                            ).date(),
                            amount=Decimal(str(tx["amount"])),
                            description=payee or description,
                            notes=description if payee and description != payee else "",
                            currency=currency.upper() if "/" not in currency else "",
                        )
                    )
            start = end
        return transactions
