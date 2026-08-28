from django.db import models

from apps.common.models import UUIDTimeStampedModel


class AssistantConversation(UUIDTimeStampedModel):
    """
    One chat thread with the in-app assistant.

    Anonymous visitors get a row too (`user` null) - the widget is available on the public
    search and marketing pages, before anyone signs in. There is no separate guest key: the
    conversation's own UUID is the only handle, it is generated server-side and returned once,
    and every later turn has to present it. That is the same "unguessable code is the
    credential" shape as the public prescription lookup (apps.eprescriptions), and it is what
    stops one visitor from resuming - and so reading back - another's thread.

    `persona` is snapshotted at creation rather than re-derived from `user.role` on each turn.
    A thread started as a shopper stays a shopper thread even if that account is later
    switched to pharmacy staff, so history written under one set of tools is never replayed
    into a wider one.
    """

    user = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="assistant_conversations",
        help_text="Null for a visitor who was not signed in when the thread started.",
    )
    persona = models.CharField(max_length=32, db_index=True, help_text="Which role's assistant this thread is talking to - see apps.assistant.personas.")
    title = models.CharField(max_length=120, blank=True, help_text="First thing the person asked, trimmed. Only for listing threads back to them.")
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self) -> str:
        return f"{self.persona} conversation {self.id}"


class AssistantMessage(UUIDTimeStampedModel):
    class Role(models.TextChoices):
        USER = "USER", "From the person"
        ASSISTANT = "ASSISTANT", "From the assistant"

    conversation = models.ForeignKey(AssistantConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    body = models.TextField()
    tools_used = models.JSONField(
        default=list,
        blank=True,
        help_text="[{name, arguments}] the assistant called to produce this reply. Kept so an answer can be traced back to the data it actually read.",
    )
    provider = models.CharField(max_length=32, blank=True, help_text="Which assistant provider produced this reply (blank on user messages).")

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.role} message on {self.conversation_id}"
