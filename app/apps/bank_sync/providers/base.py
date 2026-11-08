from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class RemoteAccount:
    id: str
    name: str
    # Currency codes as the provider spells them
    currencies: tuple = ()
    # Why the account can't be synced right now (expired connection...), empty if fine
    error: str = ""


@dataclass(frozen=True)
class RemoteTransaction:
    id: str
    date: date
    # Signed: negative is money leaving the account
    amount: Decimal
    description: str = ""
    notes: str = ""
    currency: str = ""


class BankSyncProvider(ABC):
    """A bank data aggregator.

    ``settings_fields`` declares the provider's own configuration as Django form
    fields. The service form renders them when the provider is selected and the
    values end up in ``BankSyncService.settings`` under the same keys.
    """

    settings_fields: dict = {}

    def __init__(self, settings: dict):
        self.settings = settings or {}

    @abstractmethod
    def list_accounts(self) -> list[RemoteAccount]:
        """Every account the credentials can see."""

    @abstractmethod
    def get_transactions(
        self, account_id: str, start_date: date
    ) -> list[RemoteTransaction]:
        """Posted transactions of ``account_id`` dated ``start_date`` or later."""
