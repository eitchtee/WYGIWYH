from apps.bank_sync.providers.lunchflow import LunchFlowProvider
from apps.bank_sync.providers.pluggy import PluggyProvider
from apps.bank_sync.providers.simplefin import SimpleFINProvider

# Keys must match BankSyncService.ServiceType
PROVIDER_MAPPING = {
    "lunchflow": LunchFlowProvider,
    "simplefin": SimpleFINProvider,
    "pluggy": PluggyProvider,
}
