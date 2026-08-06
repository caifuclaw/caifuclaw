# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import pytest

from app.translation_service import BaiduTranslationClient
from app.translation_settings import list_translation_language_presets


def test_translation_language_presets_use_chinese_labels_and_regional_portuguese():
    options = list_translation_language_presets()

    assert options[:7] == [
        {"code": "ru", "label": "俄语（ru）"},
        {"code": "es-419", "label": "西班牙语（拉丁美洲，es-419）"},
        {"code": "es-MX", "label": "西班牙语（墨西哥，es-MX）"},
        {"code": "pt-BR", "label": "葡萄牙语（巴西，pt-BR）"},
        {"code": "pl", "label": "波兰语（pl）"},
        {"code": "en", "label": "英语（en）"},
        {"code": "zh", "label": "中文（zh）"},
    ]
    codes = [item["code"] for item in options]
    assert len(codes) == len(set(codes))
    assert {"ara", "jp", "kor", "spa", "jav"}.issubset(set(codes))


def test_translation_language_presets_return_copies():
    options = list_translation_language_presets()
    options[0]["label"] = "changed"

    assert list_translation_language_presets()[0] == {"code": "ru", "label": "俄语（ru）"}


@pytest.mark.parametrize(
    ("business_language", "baidu_language"),
    [
        ("pt-BR", "pt"),
        ("pt-PT", "pt"),
    ],
)
def test_baidu_request_uses_supported_language_code(monkeypatch, business_language, baidu_language):
    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"trans_result": [{"src": "hello", "dst": "translated"}]}

    class FakeHttpClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, _endpoint, *, data):
            requests.append(data)
            return FakeResponse()

    monkeypatch.setattr("app.translation_service.httpx.Client", FakeHttpClient)
    client = BaiduTranslationClient(appid="demo-app", secret_key="demo-secret")

    assert client.translate_texts(["hello"], to_lang=business_language) == {"hello": "translated"}
    assert requests[0]["to"] == baidu_language
