from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ItemViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category-api")
router.register("items", ItemViewSet, basename="item-api")

urlpatterns = router.urls