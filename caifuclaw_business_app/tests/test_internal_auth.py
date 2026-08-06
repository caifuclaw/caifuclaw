# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.dependencies import create_internal_service_dependency


def test_internal_service_token_accepts_matching_token():
    dependency = create_internal_service_dependency(lambda: SimpleNamespace(internal_service_token="secret"))

    assert dependency("secret") is True


def test_internal_service_token_rejects_invalid_token():
    dependency = create_internal_service_dependency(lambda: SimpleNamespace(internal_service_token="secret"))

    with pytest.raises(HTTPException) as exc_info:
        dependency("wrong")

    assert exc_info.value.status_code == 401


def test_internal_service_token_requires_configuration():
    dependency = create_internal_service_dependency(lambda: SimpleNamespace(internal_service_token=""))

    with pytest.raises(HTTPException) as exc_info:
        dependency(None)

    assert exc_info.value.status_code == 503
