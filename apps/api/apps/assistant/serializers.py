from rest_framework import serializers

from apps.assistant.services import MAX_MESSAGE_CHARS


class AssistantChatSerializer(serializers.Serializer):
    """
    The entire accepted request body.

    There is no persona field, no role field, no history field and no system-prompt field, and
    that is the point rather than an omission: everything that decides what the assistant may
    read is derived server-side from the auth token, and everything it has said before is read
    from the database. The only thing a client contributes is one string and, optionally, the
    id of a thread it has been given.
    """

    message = serializers.CharField(max_length=MAX_MESSAGE_CHARS, trim_whitespace=True)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
