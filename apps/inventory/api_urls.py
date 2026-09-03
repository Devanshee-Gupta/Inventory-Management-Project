from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ItemViewSet, StockMovementViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category-api")
router.register("items", ItemViewSet, basename="item-api")
router.register("movements", StockMovementViewSet, basename="movement-api")

urlpatterns = router.urls