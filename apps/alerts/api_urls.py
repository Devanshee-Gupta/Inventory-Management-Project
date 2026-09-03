from rest_framework.routers import DefaultRouter

from .views import LowStockAlertViewSet

router = DefaultRouter()
router.register("alerts", LowStockAlertViewSet, basename="alert-api")

urlpatterns = router.urls