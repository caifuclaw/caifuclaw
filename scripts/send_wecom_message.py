from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CAIFUCLAW_ROOT = PROJECT_ROOT / "caifuclaw_business_app"
if str(CAIFUCLAW_ROOT) not in sys.path:
    sys.path.insert(0, str(CAIFUCLAW_ROOT))

from common.wecom_robot import WeComRobotClient, WeComRobotError, load_wecom_robot_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send messages to a WeCom group robot webhook.")
    parser.add_argument("--webhook-url", default="", help="Override [wecom_robot].webhook_url or WECOM_ROBOT_WEBHOOK_URL.")
    parser.add_argument("--json", action="store_true", help="Print the raw WeCom API response as JSON.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    text_parser = subparsers.add_parser("text", help="Send a text message.")
    text_parser.add_argument("content", nargs="?", default="", help="Text content. Reads stdin when omitted.")
    text_parser.add_argument("--content-file", default="", help="Read text content from a UTF-8 file.")
    text_parser.add_argument("--mention", action="append", default=[], help="Mention a userid. Use @all to mention all.")
    text_parser.add_argument(
        "--mention-mobile",
        action="append",
        default=[],
        help="Mention a member by mobile number. Use @all to mention all.",
    )

    image_parser = subparsers.add_parser("image", help="Send a JPG or PNG image.")
    image_parser.add_argument("path", help="Image file path.")

    file_parser = subparsers.add_parser("file", help="Upload and send a regular file.")
    file_parser.add_argument("path", help="File path.")

    excel_parser = subparsers.add_parser("excel", help="Upload and send an Excel file.")
    excel_parser.add_argument("path", help="Excel file path.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = _resolve_settings(args.webhook_url or None)
        with WeComRobotClient(settings) as client:
            response = _run_command(client, args)
    except WeComRobotError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(response, ensure_ascii=False, indent=2))
    else:
        print("Message sent successfully.")
    return 0


def _run_command(client: WeComRobotClient, args: argparse.Namespace) -> dict:
    if args.command == "text":
        content = _read_text_content(args, client.settings.default_prompt)
        return client.send_text(
            content,
            mentioned_list=args.mention,
            mentioned_mobile_list=args.mention_mobile,
        )
    if args.command == "image":
        return client.send_image(args.path)
    if args.command == "file":
        return client.send_file(args.path)
    if args.command == "excel":
        return client.send_excel(args.path)
    raise WeComRobotError(f"Unsupported command: {args.command}")


def _resolve_settings(webhook_url: str | None):
    if webhook_url:
        return load_wecom_robot_settings(webhook_url=webhook_url)
    db_error: Exception | None = None
    try:
        from app.wecom_service import load_wecom_robot_settings_from_db

        return load_wecom_robot_settings_from_db()
    except Exception as exc:
        db_error = exc
    try:
        return load_wecom_robot_settings()
    except WeComRobotError:
        if db_error is not None:
            raise WeComRobotError(str(db_error)) from db_error
        raise


def _read_text_content(args: argparse.Namespace, default_prompt: str = "") -> str:
    if args.content_file:
        return Path(args.content_file).read_text(encoding="utf-8")
    if args.content:
        return args.content
    stdin_value = sys.stdin.read()
    if stdin_value:
        return stdin_value
    return default_prompt


if __name__ == "__main__":
    raise SystemExit(main())
