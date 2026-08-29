from rest_framework import serializers

from apps.assistant.services import MAX_MESSAGE_CHARS


class AssistantChatSerializer(serializers.Serializer):
    """
    The entire accepted request body.

    There is no persona field, no role field, no history field and no system-prompt field, and
    that is the point rather than an omission: everything that decides what the assistant may
    read is derived server-side from the auth token, and everything it has said before is read
    from the database. The only thing a client contributes is one string, optionally the id of
    a thread it has been given, and optionally where the device thinks it is.

    Coordinates are the one addition to that list, and they are the same kind of thing as the
    message: search input, not identity. They decide the order results come back in and
    nothing else - no persona is widened, no record is unlocked, and a caller that lies about
    its position only mis-sorts its own answer.
    """

    message = serializers.CharField(max_length=MAX_MESSAGE_CHARS, trim_whitespace=True)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    latitude = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, allow_null=True, min_value=-180, max_value=180)
