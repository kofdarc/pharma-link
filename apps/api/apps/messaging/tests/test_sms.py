from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.messaging.sms.aws_sns import AwsSnsSmsProvider
from apps.messaging.sms.base import FAILED, SENT
from apps.messaging.sms.console import ConsoleSmsProvider
from apps.messaging.sms.registry import get_provider
from apps.messaging.sms.service import send_sms


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
