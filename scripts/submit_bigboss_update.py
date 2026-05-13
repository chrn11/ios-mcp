#!/usr/bin/env python3
"""Submit one iOS MCP .deb update request to the BigBoss update form.

The script defaults to a dry run. Add --submit to perform the external POST.
"""

from __future__ import annotations

import argparse
import html.parser
import mimetypes
import sys
import uuid
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


FORM_URL = "http://thebigboss.org/hosting-repository-cydia/update-your-app"
FORM_ID = "cforms3form"
PACKAGE_NAME = "iOS MCP"
BIGBOSS_NAME = "witchan"
BIGBOSS_EMAIL = "witchan028@126.com"
DEFAULT_RESPONSE_OUT = ".codex-session-data/bigboss_update_response.html"


class CFormsParser(html.parser.HTMLParser):
    def __init__(self, form_id: str) -> None:
        super().__init__()
        self.form_id = form_id
        self.in_form = False
        self.form_seen = False
        self.action = ""
        self.method = "post"
        self.hidden_fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: (value or "") for key, value in attrs}
        if tag.lower() == "form" and attr.get("id") == self.form_id:
            self.in_form = True
            self.form_seen = True
            self.action = attr.get("action", "")
            self.method = attr.get("method", "post").lower()
            return

        if not self.in_form or tag.lower() != "input":
            return

        if attr.get("type", "text").lower() == "hidden" and attr.get("name"):
            self.hidden_fields[attr["name"]] = attr.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if self.in_form and tag.lower() == "form":
            self.in_form = False


def strip_fragment(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def fetch_form(url: str, timeout: float) -> tuple[str, dict[str, str]]:
    request = Request(url, headers={"User-Agent": "ios-mcp-bigboss-update/1.1"})
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8", "replace")

    parser = CFormsParser(FORM_ID)
    parser.feed(html)
    if not parser.form_seen:
        raise RuntimeError(f"BigBoss update form {FORM_ID} was not found")
    if parser.method != "post":
        raise RuntimeError(f"Unexpected BigBoss form method: {parser.method}")

    action = strip_fragment(urljoin(url, parser.action or url))
    return action, parser.hidden_fields


def read_changes(args: argparse.Namespace) -> str:
    if args.changes is not None:
        return args.changes
    return Path(args.changes_file).read_text(encoding="utf-8")


def validate_deb(path: str) -> Path:
    deb = Path(path)
    if not deb.is_file():
        raise FileNotFoundError(f"deb file not found: {deb}")
    if deb.suffix != ".deb":
        raise ValueError(f"expected a .deb file: {deb}")
    return deb


def guess_content_type(path: Path) -> str:
    if path.suffix == ".deb":
        return "application/vnd.debian.binary-package"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def multipart_body(
    fields: Iterable[tuple[str, str]],
    file_field: str,
    file_path: Path,
) -> tuple[bytes, str]:
    boundary = f"----ios-mcp-bigboss-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\n'
            f"Content-Type: {guess_content_type(file_path)}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def submit_form(
    action_url: str,
    fields: list[tuple[str, str]],
    deb_path: Path,
    timeout: float,
) -> tuple[int, bytes]:
    body, boundary = multipart_body(fields, "cf_uploadfile3[]", deb_path)
    request = Request(
        action_url,
        data=body,
        method="POST",
        headers={
            "User-Agent": "ios-mcp-bigboss-update/1.1",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "Referer": FORM_URL,
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit one iOS MCP .deb package to the BigBoss update form."
    )
    parser.add_argument("deb", help="Path to the .deb package to upload.")
    parser.add_argument("--url", default=FORM_URL)
    parser.add_argument("--version", required=True)
    changes = parser.add_mutually_exclusive_group(required=True)
    changes.add_argument("--changes", help="Text for the BigBoss Changes Made field.")
    changes.add_argument("--changes-file", help="UTF-8 text file for Changes Made.")
    parser.add_argument(
        "--instructions",
        default=None,
        help="Optional maintainer instructions. Defaults to the deb filename.",
    )
    parser.add_argument("--response-out", default=DEFAULT_RESPONSE_OUT)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Actually submit to BigBoss. Without this flag, the script is dry-run only.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    deb_path = validate_deb(args.deb)
    changes = read_changes(args)
    instructions = args.instructions or f"Package contents: {deb_path.name}"

    action_url, hidden_fields = fetch_form(args.url, args.timeout)
    fields_map = dict(hidden_fields)
    fields_map.update(
        {
            "cf3_field_1": PACKAGE_NAME,
            "cf3_field_2": args.version,
            "cf3_field_3": BIGBOSS_NAME,
            "cf3_field_4": BIGBOSS_EMAIL,
            "cf3_field_5": changes,
            "cf3_field_6": instructions,
            "sendbutton3": "Submit",
        }
    )
    fields = list(fields_map.items())

    print(f"BigBoss form: {args.url}")
    print(f"POST action: {action_url}")
    print(f"Package name: {PACKAGE_NAME}")
    print(f"Version: {args.version}")
    print(f"Name: {BIGBOSS_NAME}")
    print(f"Email: {BIGBOSS_EMAIL}")
    print(f"Deb: {deb_path} ({deb_path.stat().st_size} bytes)")
    print("Changes Made:")
    print(changes)
    print("Instructions:")
    print(instructions)

    if not args.submit:
        print("Dry run only. Re-run with --submit to submit to BigBoss.")
        return 0

    status, response = submit_form(action_url, fields, deb_path, args.timeout)
    response_out = Path(args.response_out)
    response_out.parent.mkdir(parents=True, exist_ok=True)
    response_out.write_bytes(response)
    print(f"Submitted. HTTP status: {status}")
    print(f"Response saved to: {response_out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
