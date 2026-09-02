"""Safely provision BlinkPy credentials from BlinkDRS over SSH.

BlinkDRS uploads an owner-only JSON request through its verified SSH/SFTP
connection. This helper removes that request immediately after reading it,
authenticates with Blink, and atomically replaces credentials.json only after
the login and Blink system discovery succeed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink


ROOT = Path(__file__).resolve().parent
CREDENTIALS_PATH = ROOT / "config" / "credentials.json"


def emit(status: str, **details) -> None:
    """Write one machine-readable response without exposing secrets."""
    print(json.dumps({"status": status, **details}), flush=True)


def load_request(request_path: Path) -> dict:
    """Read and immediately remove the short-lived secret request."""
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    finally:
        try:
            request_path.unlink()
        except FileNotFoundError:
            pass

    if not isinstance(request, dict):
        raise ValueError("The provisioning request must be a JSON object.")

    return request


async def provision(request: dict) -> None:
    username = str(request.get("username", "")).strip()
    password = str(request.get("password", ""))
    two_factor_code = str(request.get("two_factor_code", "")).strip()

    if not username or not password:
        raise ValueError("Blink email and password are required.")

    async with ClientSession() as session:
        blink = Blink(refresh_rate=60, session=session)
        blink.auth = Auth(
            {"username": username, "password": password},
            no_prompt=True,
            session=session,
        )

        try:
            started = await blink.start()
        except BlinkTwoFARequiredError:
            if not two_factor_code:
                emit("two_factor_required")
                return

            started = await blink.send_2fa_code(two_factor_code)

        if not started or not blink.available:
            raise RuntimeError("Blink authentication did not complete.")

        if not blink.cameras:
            raise RuntimeError(
                "Blink authenticated, but no cameras were discovered."
            )

        CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = CREDENTIALS_PATH.with_suffix(".json.tmp")

        try:
            await blink.save(str(temporary_path))
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, CREDENTIALS_PATH)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

        emit(
            "success",
            cameras=len(blink.cameras),
            systems=len(blink.sync),
        )


async def main() -> int:
    if len(sys.argv) != 2:
        emit("error", message="A provisioning request path is required.")
        return 2

    request_path = Path(sys.argv[1]).expanduser().resolve()

    try:
        request = load_request(request_path)
        await provision(request)
        return 0
    except Exception as exc:
        emit("error", message=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
