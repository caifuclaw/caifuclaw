import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

EXPECTED_API_ROUTE_COUNT = 218
EXPECTED_API_ROUTE_SHA256 = "3e956548a31487f06ca03042212b7630334de2615420a90b11fac86292a7aa09"


def _route_manifest() -> list[str]:
    project_root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent(
        """
        import json
        from fastapi.routing import APIRoute
        from app.main import app

        rows = []
        frontend_route_names = {"serve_index", "serve_frontend_version", "serve_spa"}

        def iter_api_routes(routes):
            for route in routes:
                if isinstance(route, APIRoute):
                    yield route
                original_router = getattr(route, "original_router", None)
                if original_router is not None:
                    yield from iter_api_routes(original_router.routes)

        for route in iter_api_routes(app.routes):
            if route.name in frontend_route_names:
                continue
            response_model = getattr(route, "response_model", None)
            response_model_name = getattr(response_model, "__name__", str(response_model))
            rows.append(
                "|".join(
                    [
                        ",".join(sorted(route.methods or [])),
                        route.path,
                        route.name,
                        response_model_name,
                    ]
                )
            )

        print(json.dumps(sorted(rows)))
        """
    )
    env = os.environ.copy()
    env["CAIFUCLAW_AI_CONFIG_FILE"] = str(project_root / "config.template.toml")
    python_paths = [str(project_root.parent), str(project_root)]
    if existing_python_path := env.get("PYTHONPATH"):
        python_paths.append(existing_python_path)
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.splitlines()[-1])


def test_api_route_contract_is_unchanged() -> None:
    manifest = _route_manifest()
    digest = hashlib.sha256("\n".join(manifest).encode()).hexdigest()

    assert len(manifest) == EXPECTED_API_ROUTE_COUNT
    assert digest == EXPECTED_API_ROUTE_SHA256
