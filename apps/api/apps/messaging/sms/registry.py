from apps.messaging.sms.aws_sns import AwsSnsSmsProvider
from apps.messaging.sms.base import SmsProvider
from apps.messaging.sms.console import ConsoleSmsProvider

_PROVIDERS: dict[str, SmsProvider] = {
    ConsoleSmsProvider.code: ConsoleSmsProvider(),
    AwsSnsSmsProvider.code: AwsSnsSmsProvider(),
}


def get_provider(code: str) -> SmsProvider:
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ValueError(f"Unknown SMS provider '{code}'.") from None
