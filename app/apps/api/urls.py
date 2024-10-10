from django.urls import path, include
from rest_framework import routers

from apps.api import views

router = routers.DefaultRouter()
router.register(r"transactions", views.TransactionViewSet)
router.register(r"categories", views.TransactionCategoryViewSet)
router.register(r"tags", views.TransactionTagViewSet)
router.register(r"installment-plans", views.InstallmentPlanViewSet)
router.register(r"account-groups", views.AccountGroupViewSet)
router.register(r"accounts", views.AccountViewSet)
router.register(r"currencies", views.CurrencyViewSet)
router.register(r"exchange-rates", views.ExchangeRateViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
