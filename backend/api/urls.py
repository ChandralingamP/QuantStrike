from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminUserManagementView,
    AlgoConfigurationView,
    HomeConnectView,
    HomeStatusView,
    InstrumentViewSet,
    LoginView,
    ProfitLossExportView,
    ProfitLossView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PasswordResetView,
    RequestOTPView,
    SignupView,
    StrategyViewSet,
    StrategyAlphaRunView,
    StrategyOneBacktestView,
)
from .views_logs import LogFilesListView, LogFileContentView

router = DefaultRouter()
router.register(r"strategies", StrategyViewSet, basename="strategy")
router.register(r"instruments", InstrumentViewSet, basename="instrument")

urlpatterns = [
    path("auth/request-otp/", RequestOTPView.as_view(), name="request-otp"),
    path("auth/signup/", SignupView.as_view(), name="signup"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path(
        "auth/password/request-reset/",
        PasswordResetRequestView.as_view(),
        name="password-request-reset",
    ),
    path(
        "auth/password/verify-otp/",
        PasswordResetVerifyView.as_view(),
        name="password-verify-otp",
    ),
    path(
        "auth/password/reset/",
        PasswordResetView.as_view(),
        name="password-reset",
    ),
    path(
        "auth/admin/users/",
        AdminUserManagementView.as_view(),
        name="admin-users",
    ),
    path("algo/config", AlgoConfigurationView.as_view(), name="algo-config"),
    path("home/status/", HomeStatusView.as_view(), name="home-status"),
    path("home/connect/", HomeConnectView.as_view(), name="home-connect"),
    path("pnl", ProfitLossView.as_view(), name="pnl-list"),
    path("pnl/export", ProfitLossExportView.as_view(), name="pnl-export"),
    path(
        "strategy/alpha/run",
        StrategyAlphaRunView.as_view(),
        name="strategy-alpha-run",
    ),
    path(
        "strategy/one/backtest/",
        StrategyOneBacktestView.as_view(),
        name="strategy-one-backtest",
    ),
    path("logs/files/", LogFilesListView.as_view(), name="log-files-list"),
    path("logs/content/", LogFileContentView.as_view(), name="log-file-content"),
    path("", include(router.urls)),
]
