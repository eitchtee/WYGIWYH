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
router.register(r"currencies", views.CurrencyViewSet)
router.register(r"exchange-rates", views.ExchangeRateViewSet)
router.register(r"dca/strategies", views.DCAStrategyViewSet)
router.register(r"dca/entries", views.DCAEntryViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
