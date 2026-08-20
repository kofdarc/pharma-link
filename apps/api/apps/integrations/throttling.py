from rest_framework.throttling import SimpleRateThrottle


class IntegrationKeyThrottle(SimpleRateThrottle):
    """
    Scopes the machine API's rate limit to the resolved integration key's pharmacy instead
    of the caller's IP: a compromised key cannot dodge the limit by rotating source IPs, and
    one pharmacy's traffic can never eat into another pharmacy's budget.
    """

    scope = "integration_api"

    def get_cache_key(self, request, view):
        identity = getattr(request, "user", None)
        pharmacy_id = getattr(identity, "pharmacy_id", None)
        if not pharmacy_id:
            # Unauthenticated - IntegrationKeyAuthentication/HasIntegrationScope reject this
            # request on their own; nothing meaningful to scope a rate limit to here.
            return None
        return self.cache_format % {"scope": self.scope, "ident": pharmacy_id}
