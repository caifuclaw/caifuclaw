# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import asyncio
import io
import zipfile

import pytest
from fastapi import HTTPException

import app.main as main_module
from app.schemas import AiImageBatchDownloadRequest, AiImageDownloadItem


class StubOssObject:
    headers = {"Content-Type": "image/png", "Content-Length": "6"}

    def __init__(self):
        self._chunks = iter([b"abc", b"def", b""])
        self.closed = False

    def read(self, _size):
        return next(self._chunks)

    def close(self):
        self.closed = True


def test_ai_image_download_rejects_objects_outside_toolbox():
    invalid_keys = [
        "other/image.png",
        "ai_toolbox/../secret.png",
        "ai_toolbox/job\\secret.png",
        "ai_toolbox//image.png",
    ]

    for object_key in invalid_keys:
        with pytest.raises(HTTPException) as exc_info:
            main_module._validated_ai_image_object_key(object_key)
        assert exc_info.value.status_code == 400


def test_ai_image_download_streams_attachment_and_closes_object(monkeypatch):
    object_key = "ai_toolbox/2026/07/31/job/outputs/01-image.png"
    result = StubOssObject()
    monkeypatch.setattr(main_module, "_open_ai_image_oss_object", lambda key: result)

    response = main_module.download_ai_image(
        object_key=object_key,
        filename="处理结果.png",
        _=object(),
    )

    assert response.media_type == "image/png"
    assert response.headers["content-length"] == "6"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert b"".join(main_module._iter_ai_image_oss_object(result)) == b"abcdef"
    assert result.closed is True


def test_batch_download_builds_zip_and_deduplicates_names(monkeypatch):
    payloads = {
        "ai_toolbox/2026/08/02/job/outputs/01-image.png": b"first",
        "ai_toolbox/2026/08/02/job/outputs/02-image.png": b"second",
    }
    monkeypatch.setattr(main_module, "_open_ai_image_oss_object", lambda key: io.BytesIO(payloads[key]))

    response = main_module.download_ai_images_batch(
        AiImageBatchDownloadRequest(
            items=[
                AiImageDownloadItem(object_key=key, filename="image.png")
                for key in payloads
            ]
        ),
        None,
    )

    async def collect_body():
        return b"".join([chunk async for chunk in response.body_iterator])

    with zipfile.ZipFile(io.BytesIO(asyncio.run(collect_body()))) as archive:
        assert archive.namelist() == ["image.png", "image (2).png"]
        assert archive.read("image.png") == b"first"
        assert archive.read("image (2).png") == b"second"

    assert response.media_type == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
