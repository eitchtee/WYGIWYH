from apps.bank_sync.providers.lunchflow import LunchFlowProvider

# Keys must match BankSyncService.ServiceType
PROVIDER_MAPPING = {
    "lunchflow": LunchFlowProvider,
}
