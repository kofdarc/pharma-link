from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from django.utils import timezone

from apps.notifications.services import feed_for


class NotificationsView(APIView):
    """
    The signed-in user's in-app notification feed, computed fresh on each call.

    The web client polls this on an interval while a tab is open and de-dupes
    client-side, so it is a plain read with no "mark read" side effect. Scoped
    throttle keeps a stuck polling loop from hammering the API.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "notifications"

    def get(self, request):
        return Response(
            {
                "notifications": feed_for(request.user),
                "generated_at": timezone.now().isoformat(),
            }
        )
