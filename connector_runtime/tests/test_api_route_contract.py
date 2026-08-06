# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import hashlib

from fastapi.routing import APIRoute

from app.main import app


EXPECTED_ROUTE_COUNT = 11
EXPECTED_ROUTE_SHA256 = "5e85737ccdbfae3e36667620a624af3c93b062d657486d10298237f5d4bc4921"


def test_connector_runtime_route_contract_is_unchanged() -> None:
    def iter_api_routes(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                yield route

            # FastAPI 0.141+ retains included routers as nested route objects.
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                yield from iter_api_routes(original_router.routes)

    manifest = sorted(
        "|".join(
            [
                ",".join(sorted(route.methods or [])),
                route.path,
                route.name,
                getattr(
                    getattr(route, "response_model", None),
                    "__name__",
                    str(getattr(route, "response_model", None)),
                ),
            ]
        )
        for route in iter_api_routes(app.routes)
    )

    assert len(manifest) == EXPECTED_ROUTE_COUNT
    assert hashlib.sha256("\n".join(manifest).encode()).hexdigest() == EXPECTED_ROUTE_SHA256
