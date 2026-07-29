"""
Create and save valid Blink credentials.

This program saves credentials only after Blink authentication,
any required 2FA, system setup, and camera discovery have completed
successfully.
"""

import asyncio

import getpass
from pathlib import Path

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink


CREDS_PATH = Path("config/credentials.json")


async def main() -> None:
    username = input("Blink email: ").strip()
    password = getpass.getpass("Blink password: ")

    if not username or not password:
        raise RuntimeError("Blink email and password are required.")

    async with ClientSession() as session:
        blink = Blink(
            refresh_rate=60,
            session=session,
        )

        blink.auth = Auth(
            {
                "username": username,
                "password": password,
            },
            no_prompt=True,
            session=session,
        )

        try:
            started = await blink.start()

        except BlinkTwoFARequiredError:
            print()
            print("2FA required. Check your email or phone for a Blink code.")

            code = input("Enter the Blink 2FA code: ").strip()

            if not code:
                raise RuntimeError("No 2FA code was entered.")

            # Complete 2FA and continue Blink system setup.
            started = await blink.send_2fa_code(code)

        if not started:
            raise RuntimeError(
                "Blink login or system setup did not complete successfully."
            )

        if not blink.available:
            raise RuntimeError(
                "Blink reported that the account is unavailable."
            )

        if not blink.cameras:
            raise RuntimeError(
                "Blink authenticated, but no cameras were discovered. "
                "Credentials will not be saved."
            )

        CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)

        await blink.save(str(CREDS_PATH))

        print()
        print("=" * 60)
        print(f"SUCCESS! Saved credentials to {CREDS_PATH}")
        print(f"Found {len(blink.cameras)} camera(s):")

        for camera_name, camera in blink.cameras.items():
            print(
                f"  {camera_name} "
                f"({type(camera).__name__})"
            )

        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())