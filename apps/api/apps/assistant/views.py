from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.assistant import personas, services
from apps.assistant.serializers import AssistantChatSerializer


class AssistantAnonThrottle(AnonRateThrottle):
    scope = "assistant"


class AssistantUserThrottle(UserRateThrottle):
    scope = "assistant"


class AssistantSessionView(APIView):
    """
    What the widget needs before anyone has typed anything: which assistant this visitor is
    talking to, how it opens, and what it can be asked.

    Open to anonymous visitors because the widget is on the public pages too - a signed-out
    caller gets the guest persona, which reaches no personal data at all.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AssistantAnonThrottle, AssistantUserThrottle]

    def get(self, request):
        persona = personas.persona_for(request.user)
        return Response(
            {
                "persona": persona.key,
                "label": persona.label,
                "greeting": persona.greeting,
                "suggestions": list(persona.suggestions),
                "signed_in": bool(request.user and request.user.is_authenticated),
            }
        )


class AssistantChatView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AssistantAnonThrottle, AssistantUserThrottle]

    def post(self, request):
        serializer = AssistantChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        conversation = None
        conversation_id = serializer.validated_data.get("conversation_id")
        if conversation_id:
            try:
                conversation = services.load_conversation(str(conversation_id), request.user)
            except services.ConversationNotFound:
                # Deliberately indistinguishable from "never existed". Telling a caller that an
                # id is real but not theirs turns the id space into an oracle.
                return Response({"detail": "No such conversation."}, status=status.HTTP_404_NOT_FOUND)

        try:
            payload = services.answer(
                user=request.user,
                message=serializer.validated_data["message"],
                conversation=conversation,
                latitude=serializer.validated_data.get("latitude"),
                longitude=serializer.validated_data.get("longitude"),
            )
        except services.ConversationNotFound:
            return Response({"detail": "No such conversation."}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)
