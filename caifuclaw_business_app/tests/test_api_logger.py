# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from app.api_logger import _redact


def test_redact_masks_snake_case_and_camel_case_secret_keys():
    value = _redact(
        {
            "access_token": "secret-a",
            "accessToken": "secret-b",
            "refreshToken": "secret-c",
            "clientSecret": "secret-d",
            "authorization": "Bearer secret-e",
            "safe_value": "visible",
        }
    )

    assert value == {
        "access_token": "***",
        "accessToken": "***",
        "refreshToken": "***",
        "clientSecret": "***",
        "authorization": "***",
        "safe_value": "visible",
    }
