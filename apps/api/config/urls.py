from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(_request):
    return Response({"status": "ok", "service": "pharmalink-api"})


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/health/", health_check),
    path("api/", include("apps.api_urls.urls")),
]

if settings.DEBUG:
    # Product images only - prescriptions are served through the app, never as plain static files.
    urlpatterns += static(settings.PUBLIC_MEDIA_URL, document_root=settings.PUBLIC_MEDIA_ROOT)

