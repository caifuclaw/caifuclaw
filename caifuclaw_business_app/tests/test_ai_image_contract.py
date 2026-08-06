import ast
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _class_fields(path: Path, class_name: str) -> set[str]:
    module = ast.parse(path.read_text(encoding="utf-8-sig"))
    class_node = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        node.target.id for node in class_node.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }


def _function_parameters(path: Path, function_name: str) -> set[str]:
    module = ast.parse(path.read_text(encoding="utf-8-sig"))
    function_node = next(
        node for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    return {argument.arg for argument in function_node.args.args}


def test_ai_image_process_contract_has_no_image_rule_fields():
    request_fields = _function_parameters(APP_DIR / "main.py", "process_ai_image")
    response_fields = _class_fields(APP_DIR / "schemas.py", "AiImageProcessResponse")

    assert "apply_rule" not in request_fields
    assert "rule_id" not in request_fields
    assert not {"rule_id", "rule_name", "rule_profile_key", "rule_execution"} & response_fields
