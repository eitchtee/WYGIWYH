from django.urls import path, include
from rest_framework import routers

from apps.api import views

router = routers.DefaultRouter()
router.register(r"transactions", views.TransactionViewSet)
router.register(r"categories", views.TransactionCategoryViewSet)
router.register(r"tags", views.TransactionTagViewSet)
router.register(r"entities", views.TransactionEntityViewSet)
router.register(r"installment-plans", views.InstallmentPlanViewSet)
router.register(r"recurring-transactions", views.RecurringTransactionViewSet)
router.register(r"account-groups", views.AccountGroupViewSet)
router.register(r"accounts", views.AccountViewSet)
router.register(r"investment-classes", views.InvestmentClassViewSet)
router.register(r"currencies", views.CurrencyViewSet)
router.register(r"exchange-rates", views.ExchangeRateViewSet)
router.register(r"dca/strategies", views.DCAStrategyViewSet)
router.register(r"dca/entries", views.DCAEntryViewSet)
router.register(r"splits/events", views.SplitEventViewSet, basename="split-events")
router.register(r"splits/participants", views.SplitParticipantViewSet, basename="split-participants")
router.register(r"splits/expenses", views.SplitExpenseViewSet, basename="split-expenses")
router.register(r"splits/payments", views.SplitPaymentViewSet, basename="split-payments")
router.register(r"import/profiles", views.ImportProfileViewSet, basename="import-profiles")
router.register(r"import/runs", views.ImportRunViewSet, basename="import-runs")
router.register(r"import/import", views.ImportViewSet, basename="import-import")

urlpatterns = [
    path("", include(router.urls)),
]

