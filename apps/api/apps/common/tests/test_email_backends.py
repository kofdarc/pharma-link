from unittest.mock import MagicMock, patch

from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from apps.common.email_backends import SESEmailBackend


def _message() -> EmailMultiAlternatives:
    msg = EmailMultiAlternatives(
        subject="Prescription RX-1",
        body="text body",
        from_email="HealthConnect <no-reply@healthconnect.dev>",
        to=["patient@example.test"],
    )
    msg.attach_alternative("<p>html body</p>", "text/html")
    msg.attach("prescription-RX-1.svg", "<svg/>", "image/svg+xml")
    return msg


@override_settings(AWS_SES_REGION_NAME="eu-central-1", SES_CONFIGURATION_SET="")
class SESEmailBackendTests(SimpleTestCase):
    def test_sends_raw_mime_preserving_html_and_attachment(self):
        fake_client = MagicMock()

        with patch("boto3.client", return_value=fake_client) as mock_boto:
            sent = SESEmailBackend().send_messages([_message()])

        self.assertEqual(sent, 1)
        mock_boto.assert_called_once_with("sesv2", region_name="eu-central-1")
        kwargs = fake_client.send_email.call_args.kwargs
        self.assertEqual(kwargs["FromEmailAddress"], "HealthConnect <no-reply@healthconnect.dev>")
        self.assertEqual(kwargs["Destination"]["ToAddresses"], ["patient@example.test"])
        raw = kwargs["Content"]["Raw"]["Data"]
        self.assertIn(b"prescription-RX-1.svg", raw)
        self.assertIn(b"text/html", raw)
        self.assertNotIn("ConfigurationSetName", kwargs)

    @override_settings(SES_CONFIGURATION_SET="pharmalink-events")
    def test_configuration_set_is_passed_when_set(self):
        fake_client = MagicMock()
        with patch("boto3.client", return_value=fake_client):
            SESEmailBackend().send_messages([_message()])
        self.assertEqual(fake_client.send_email.call_args.kwargs["ConfigurationSetName"], "pharmalink-events")

    def test_fail_silently_swallows_client_error(self):
        from botocore.exceptions import ClientError

        fake_client = MagicMock()
        fake_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "Email address not verified"}}, "SendEmail"
        )

        with patch("boto3.client", return_value=fake_client):
            sent = SESEmailBackend(fail_silently=True).send_messages([_message()])

        self.assertEqual(sent, 0)

    def test_client_error_propagates_when_not_fail_silently(self):
        from botocore.exceptions import ClientError

        fake_client = MagicMock()
        fake_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "nope"}}, "SendEmail"
        )

        with patch("boto3.client", return_value=fake_client):
            with self.assertRaises(ClientError):
                SESEmailBackend(fail_silently=False).send_messages([_message()])
