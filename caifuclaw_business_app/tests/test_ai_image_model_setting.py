# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from types import SimpleNamespace

from app import main as main_module
from app.models import ModelEndpoint, ModelSetting
from app.schemas import ModelSettingUpsertRequest


class _FakeDb:
    def __init__(self) -> None:
        self.endpoint = SimpleNamespace(id=9)
        self.setting = SimpleNamespace(
            id=3,
            name="vision model",
            model="vision-test",
            endpoint_id=9,
            enabled=True,
            is_default=False,
            supports_vision=False,
        )
        self.committed = False

    def get(self, model, row_id):
        if model is ModelSetting and row_id == self.setting.id:
            return self.setting
        if model is ModelEndpoint and row_id == self.endpoint.id:
            return self.endpoint
        return None

    def scalar(self, _query):
        return None

    def commit(self) -> None:
        self.committed = True

    def refresh(self, _row, attribute_names=None) -> None:
        return None


def test_update_model_setting_persists_vision_capability(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(main_module, "_model_setting_dto", lambda row: row)

    result = main_module.update_model_setting(
        3,
        ModelSettingUpsertRequest(
            name="vision model",
            model="vision-test",
            endpoint_id=9,
            enabled=True,
            is_default=False,
            supports_vision=True,
        ),
        SimpleNamespace(),
        db,
    )

    assert result.supports_vision is True
    assert db.setting.supports_vision is True
    assert db.committed is True
