from rest_framework.permissions import BasePermission

from apps.integrations.authentication import IntegrationIdentity


class HasIntegrationScope(BasePermission):
    """Machine endpoints: authenticated by signature and holding the required scope."""

    required_scope: str = ""

    def has_permission(self, request, view) -> bool:
        identity = request.user
        if not isinstance(identity, IntegrationIdentity):
            return False
        scope = getattr(view, "required_scope", self.required_scope)
        return bool(scope) and identity.integration_key.has_scope(scope)
