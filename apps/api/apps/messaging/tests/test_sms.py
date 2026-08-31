import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.messaging.sms.aws_sns import AwsSnsSmsProvider
from apps.messaging.sms.base import FAILED, SENT
from apps.messaging.sms.console import ConsoleSmsProvider
from apps.messaging.sms.registry import get_provider
from apps.messaging.sms.service import send_sms
from apps.messaging.sms.twilio import TwilioSmsProvider


class ConsoleSmsProviderTests(SimpleTestCase):
    def test_send_text_reports_sent(self):
        result = ConsoleSmsProvider().send_text(to="+96170123456", body="hello")

        self.assertEqual(result.status, SENT)
        self.assertTrue(result.provider_message_id.startswith("console-sms-"))


class RegistryTests(SimpleTestCase):
    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            get_provider("carrier-pigeon")


class SendSmsChokepointTests(SimpleTestCase):
    def test_blank_recipient_fails_without_raising(self):
        result = send_sms(to="", body="hi")
        self.assertEqual(result.status, FAILED)

    def test_unparseable_number_fails_without_raising(self):
        result = send_sms(to="not a phone", body="hi")
        self.assertEqual(result.status, FAILED)

    @override_settings(SMS_PROVIDER="console")
    def test_number_is_normalized_to_e164_before_the_provider_sees_it(self):
        with patch.object(ConsoleSmsProvider, "send_text", return_value=MagicMock(status=SENT)) as mock_send:
            send_sms(to="+961 70 123 456", body="hi")

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["to"], "+96170123456")


@override_settings(SMS_PROVIDER="aws_sns", SMS_SENDER_ID="HealthCnct", AWS_SNS_REGION_NAME="eu-central-1")
class AwsSnsSmsProviderTests(SimpleTestCase):
    def test_publish_is_called_with_transactional_type_and_sender_id(self):
        fake_client = MagicMock()
        fake_client.publish.return_value = {"MessageId": "sns-abc-123"}

        with patch("boto3.client", return_value=fake_client) as mock_boto:
            result = AwsSnsSmsProvider().send_text(to="+96170123456", body="your prescription")

        mock_boto.assert_called_once_with("sns", region_name="eu-central-1")
        kwargs = fake_client.publish.call_args.kwargs
        self.assertEqual(kwargs["PhoneNumber"], "+96170123456")
        self.assertEqual(kwargs["Message"], "your prescription")
        self.assertEqual(kwargs["MessageAttributes"]["AWS.SNS.SMS.SMSType"]["StringValue"], "Transactional")
        self.assertEqual(kwargs["MessageAttributes"]["AWS.SNS.SMS.SenderID"]["StringValue"], "HealthCnct")
        self.assertEqual(result.status, SENT)
        self.assertEqual(result.provider_message_id, "sns-abc-123")

    def test_client_error_is_reported_as_failed(self):
        from botocore.exceptions import ClientError

        fake_client = MagicMock()
        fake_client.publish.side_effect = ClientError({"Error": {"Code": "Throttling", "Message": "slow down"}}, "Publish")

        with patch("boto3.client", return_value=fake_client):
            result = AwsSnsSmsProvider().send_text(to="+96170123456", body="x")

        self.assertEqual(result.status, FAILED)
        self.assertIn("Throttling", result.failure_reason)

    @override_settings(SMS_SENDER_ID="")
    def test_sender_id_is_omitted_when_unset(self):
        fake_client = MagicMock()
        fake_client.publish.return_value = {"MessageId": "id"}

        with patch("boto3.client", return_value=fake_client):
            AwsSnsSmsProvider().send_text(to="+96170123456", body="x")

        self.assertNotIn("AWS.SNS.SMS.SenderID", fake_client.publish.call_args.kwargs["MessageAttributes"])


def _http_response(payload: dict):
    return io.BytesIO(json.dumps(payload).encode())


@override_settings(
    SMS_PROVIDER="twilio",
    TWILIO_ACCOUNT_SID="AC_test",
    TWILIO_AUTH_TOKEN="tok_test",
    TWILIO_FROM="+15005550006",
)
class TwilioSmsProviderTests(SimpleTestCase):
    def test_posts_form_encoded_message_and_reports_sent(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = request.data.decode()
            return _http_response({"sid": "SM123", "status": "queued"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = TwilioSmsProvider().send_text(to="+96170123456", body="Rx RJQX")

        self.assertIn("/Accounts/AC_test/Messages.json", captured["url"])
        self.assertTrue(captured["auth"].startswith("Basic "))
        self.assertIn("To=%2B96170123456", captured["body"])
        self.assertIn("From=%2B15005550006", captured["body"])
        self.assertEqual(result.status, SENT)
        self.assertEqual(result.provider_message_id, "SM123")

    def test_messaging_service_sid_goes_in_its_own_field(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = request.data.decode()
            return _http_response({"sid": "SM1", "status": "accepted"})

        with override_settings(TWILIO_FROM="MG0000000000000000000000000000dead"):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                TwilioSmsProvider().send_text(to="+96170123456", body="x")

        self.assertIn("MessagingServiceSid=MG", captured["body"])
        self.assertNotIn("From=", captured["body"])

    def test_http_error_is_reported_as_failed(self):
        err = urllib.error.HTTPError("url", 400, "Bad Request", {}, io.BytesIO(b'{"message":"not a valid phone number"}'))
        with patch("urllib.request.urlopen", side_effect=err):
            result = TwilioSmsProvider().send_text(to="bad", body="x")

        self.assertEqual(result.status, FAILED)
        self.assertIn("400", result.failure_reason)

    def test_explicit_failed_status_in_body_is_a_failure(self):
        with patch("urllib.request.urlopen", side_effect=lambda r, timeout=None: _http_response(
            {"sid": "SM9", "status": "failed", "error_message": "Landline or unreachable carrier"}
        )):
            result = TwilioSmsProvider().send_text(to="+96170123456", body="x")

        self.assertEqual(result.status, FAILED)
        self.assertIn("unreachable", result.failure_reason)

    @override_settings(TWILIO_ACCOUNT_SID="", TWILIO_AUTH_TOKEN="", TWILIO_FROM="")
    def test_unconfigured_provider_fails_cleanly(self):
        result = TwilioSmsProvider().send_text(to="+96170123456", body="x")
        self.assertEqual(result.status, FAILED)
        self.assertIn("not fully configured", result.failure_reason)
