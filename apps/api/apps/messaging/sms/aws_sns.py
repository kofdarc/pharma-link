from __future__ import annotations

import logging

from django.conf import settings

from apps.messaging.sms.base import FAILED, SENT, SmsProvider, SmsResult

logger = logging.getLogger(__name__)


class AwsSnsSmsProvider(SmsProvider):
    """
    Real send via AWS SNS `Publish` to a bare phone number (no topic). Every message is
    flagged Transactional so it is never dropped as promotional. boto3 resolves credentials
    from the environment / instance role exactly like the S3 config in config/settings.py -
    nothing secret is handled here. Blank by default: only reachable once SMS_PROVIDER is set
    to "aws_sns".
    """

    code = "aws_sns"

    def send_text(self, *, to: str, body: str) -> SmsResult:
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError as exc:  # pragma: no cover - boto3 is a declared dependency
            return SmsResult(status=FAILED, failure_reason=f"boto3 unavailable: {exc}"[:255])

        attributes = {
            "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
        }
        if settings.SMS_SENDER_ID:
            attributes["AWS.SNS.SMS.SenderID"] = {"DataType": "String", "StringValue": settings.SMS_SENDER_ID}

        try:
            client = boto3.client("sns", region_name=settings.AWS_SNS_REGION_NAME or None)
            response = client.publish(PhoneNumber=to, Message=body, MessageAttributes=attributes)
        except (BotoCoreError, ClientError) as exc:
            logger.warning("SMS[aws_sns] publish to %s failed: %s", to, exc)
            return SmsResult(status=FAILED, failure_reason=str(exc)[:255])
        return SmsResult(status=SENT, provider_message_id=response.get("MessageId", ""), raw=response)
