from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BookViewSet,
    CommodityViewSet,
    CommodityPurchaseViewSet,
    SwapRequestViewSet,
    CoinPackageViewSet,
    PaymentViewSet,
    UserRegistrationView,
    UserLoginView,
    UserLogoutView,
    UserProfileView,
    CreatePaymentView,
    PaymentVerificationView,
    UserBalanceView,
    TransactionHistoryView,
    ZCoinCalculatorView,
    SessionCheckView,
    CSRFView
)

router = DefaultRouter()
router.register(r'books', BookViewSet, basename='book')
router.register(r'commodities', CommodityViewSet, basename='commodity')
router.register(r'commodity-purchases', CommodityPurchaseViewSet, basename='commoditypurchase')
router.register(r'swap-requests', SwapRequestViewSet, basename='swaprequest')
router.register(r'coin-packages', CoinPackageViewSet, basename='coins')
router.register(r'payment', PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
    
    # Authentication
    path('csrf/', CSRFView.as_view(), name='csrf_token'),
    path('auth/register/', UserRegistrationView.as_view(), name='register'),
    path('auth/login/', UserLoginView.as_view(), name='login'),
    path('auth/logout/', UserLogoutView.as_view(), name='logout'),
    path('auth/profile/', UserProfileView.as_view(), name='profile'),
    path('auth/session-check/', SessionCheckView.as_view(), name='session-check'),
    
    # Payments and Balance
    path('payments/create/', CreatePaymentView.as_view(), name='create-payment'),
    path('payments/verify/', PaymentVerificationView.as_view(), name='verify-payment'),
    path('balance/', UserBalanceView.as_view(), name='user-balance'),
    path('transactions/', TransactionHistoryView.as_view(), name='transaction-history'),
    
    # Utilities
    path('calculate-zcoin/', ZCoinCalculatorView.as_view(), name='calculate-zcoin'),
]