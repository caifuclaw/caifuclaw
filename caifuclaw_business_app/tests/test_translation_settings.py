import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.credential_manager import CredentialManager, init_credential_manager
from app.database import Base
from app.models import TranslationProviderSetting
from app.translation_service import BaiduTranslationClient, TranslationUnavailable, baidu_target_language
from app.translation_settings import (
    build_translation_client_from_setting,
    decrypt_translation_secret_key,
    encrypt_translation_secret_key,
    get_translation_provider_setting,
)


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[TranslationProviderSetting.__table__])
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _credential_manager(monkeypatch):
    init_credential_manager(CredentialManager.generate_key())
    monkeypatch.setattr(BaiduTranslationClient, "from_config", staticmethod(lambda: BaiduTranslationClient()))


def test_translation_provider_setting_creates_baidu_default():
    session_factory = _session_factory()
    with session_factory() as db:
        row = get_translation_provider_setting(db)

        assert row.provider == "baidu"
        assert row.provider_name == "百度翻译"
        assert row.enabled is False
        assert row.source_language == "auto"


def test_translation_provider_client_uses_database_credentials():
    session_factory = _session_factory()
    with session_factory() as db:
        row = get_translation_provider_setting(db)
        row.enabled = True
        row.app_id = "demo-app"
        row.encrypted_secret_key = encrypt_translation_secret_key("demo-secret")
        row.endpoint = "https://example.test/translate"
        row.timeout_seconds = 12
        row.max_retries = 3
        row.batch_size = 7
        row.batch_chars = 900
        db.commit()

        client = build_translation_client_from_setting(row)

        assert decrypt_translation_secret_key(row) == "demo-secret"
        assert client.available is True
        assert client.appid == "demo-app"
        assert client.secret_key == "demo-secret"
        assert client.endpoint == "https://example.test/translate"
        assert client.timeout == 12
        assert client.max_retries == 3
        assert client.batch_size == 7
        assert client.batch_chars == 900


def test_disabled_translation_provider_client_raises_unavailable():
    session_factory = _session_factory()
    with session_factory() as db:
        row = get_translation_provider_setting(db)
        client = build_translation_client_from_setting(row)

        with pytest.raises(TranslationUnavailable):
            client.translate_texts(["hello"], to_lang="ru")


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("es", "spa"),
        ("es-419", "spa"),
        ("es-MX", "spa"),
        ("es_ES", "spa"),
        ("spa", "spa"),
        ("pt-BR", "pt"),
    ],
)
def test_baidu_target_language_normalizes_supported_locale_codes(language, expected):
    assert baidu_target_language(language) == expected


def test_baidu_translation_client_preserves_multiline_text(monkeypatch):
    requests = []

    class FakeResponse:
        def __init__(self, query):
            self.query = query

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "trans_result": [
                    {"src": line, "dst": f"RU:{line}"}
                    for line in self.query.split("\n")
                ]
            }

    class FakeHttpClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, _endpoint, *, data):
            requests.append(data)
            return FakeResponse(data["q"])

    monkeypatch.setattr("app.translation_service.httpx.Client", FakeHttpClient)
    client = BaiduTranslationClient(appid="demo-app", secret_key="demo-secret")
    source = "First paragraph.\n\nSecond paragraph.\n[Includes]:\nItem one"

    translated = client.translate_texts([source], to_lang="ru")

    assert [request["q"] for request in requests] == [
        "First paragraph.\nSecond paragraph.\n[Includes]:\nItem one"
    ]
    assert requests[0]["to"] == "ru"
    assert translated[source] == "RU:First paragraph.\n\nRU:Second paragraph.\nRU:[Includes]:\nRU:Item one"


def test_baidu_translation_client_sends_spanish_locale_as_spa(monkeypatch):
    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"trans_result": [{"src": "Product title", "dst": "Titulo del producto"}]}

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

    translated = client.translate_texts(["Product title"], to_lang="es-419")

    assert requests[0]["to"] == "spa"
    assert translated["Product title"] == "Titulo del producto"
