from rest_framework.routers import DefaultRouter

from .views import AssignmentViewSet, LocationViewSet

router = DefaultRouter()
router.register("locations", LocationViewSet, basename="location-api")
router.register("assignments", AssignmentViewSet, basename="assignment-api")

urlpatterns = router.urls