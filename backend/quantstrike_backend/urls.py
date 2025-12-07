from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthcheck_view(_request):
    """Serve the root URL with a basic status payload."""
    return JsonResponse({"message": "Server runs and connection made"})

urlpatterns = [
    path("", healthcheck_view, name="root"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
