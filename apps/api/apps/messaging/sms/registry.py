from apps.messaging.sms.aws_sns import AwsSnsSmsProvider
from apps.messaging.sms.base import SmsProvider
from apps.messaging.sms.console import ConsoleSmsProvider
from apps.messaging.sms.twilio import TwilioSmsProvider

_PROVIDERS: dict[str, SmsProvider] = {
    ConsoleSmsProvider.code: ConsoleSmsProvider(),
    AwsSnsSmsProvider.code: AwsSnsSmsProvider(),
    TwilioSmsProvider.code: TwilioSmsProvider(),
}


def get_provider(code: str) -> SmsProvider:
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ValueError(f"Unknown SMS provider '{code}'.") from None
