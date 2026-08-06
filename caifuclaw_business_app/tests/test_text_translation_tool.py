import pytest
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.main as main_module
from app.credential_manager import CredentialManager, init_credential_manager
from app.database import Base
from app.models import LocalUser, TranslationProviderSetting
from app.schemas import TextTranslationRequest
from app.translation_service import BaiduTranslationClient
from app.translation_settings import get_translation_provider_setting


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[TranslationProviderSetting.__table__])
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _credential_manager(monkeypatch):
    init_credential_manager(CredentialManager.generate_key())
    monkeypatch.setattr(
        "app.translation_settings.BaiduTranslationClient.from_config",
        staticmethod(lambda: BaiduTranslationClient()),
    )


def test_translate_text_once_calls_client_and_logs(monkeypatch):
    session_factory = _session_factory()
    calls = []
    logs = []

    class FakeTranslationClient:
        def translate_texts(self, texts, *, from_lang="auto", to_lang="en"):
            calls.append({"texts": texts, "from_lang": from_lang, "to_lang": to_lang})
            return {texts[0]: "Hello world"}

    monkeypatch.setattr(main_module, "build_translation_client_from_setting", lambda _row: FakeTranslationClient())
    monkeypatch.setattr(main_module, "log_api_call", lambda **kwargs: logs.append(kwargs))

    with session_factory() as db:
        row = get_translation_provider_setting(db)
        row.enabled = True
        row.app_id = "demo-app"
        row.endpoint = "https://example.test/translate"
        db.commit()

        response = main_module._translate_text_once(
            TextTranslationRequest(text="  你好世界  ", source_language="auto", target_language="en"),
            user=LocalUser(id=7, username="operator", display_name="Operator"),
            db=db,
        )

    assert response.status == "success"
    assert response.translated_text == "Hello world"
    assert response.source_char_count == 4
    assert calls == [{"texts": ["你好世界"], "from_lang": "auto", "to_lang": "en"}]
    assert len(logs) == 1
    assert logs[0]["platform"] == "baidu_translate"
    assert logs[0]["operation"] == "text_translation"
    assert logs[0]["status"] == "success"
    assert logs[0]["request_body"]["q"] == "你好世界"
    assert logs[0]["response_body"] == {"translated_text": "Hello world"}
    assert logs[0]["extra"]["username"] == "operator"


def test_translate_text_once_rejects_auto_target_language(monkeypatch):
    session_factory = _session_factory()
    monkeypatch.setattr(main_module, "log_api_call", lambda **_kwargs: None)

    with session_factory() as db:
        with pytest.raises(main_module.HTTPException) as exc_info:
            main_module._translate_text_once(
                TextTranslationRequest(text="hello", source_language="auto", target_language="auto"),
                user=LocalUser(id=7, username="operator"),
                db=db,
            )

    assert exc_info.value.status_code == 422
    assert "target_language不能为auto" in str(exc_info.value.detail)
