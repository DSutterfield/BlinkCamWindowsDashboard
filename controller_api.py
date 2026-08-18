"""
controller_api.py

Blink Management System - Pi Controller API

Provides the network interface between the Raspberry Pi Blink Controller
and the Windows Management Console.

API Version: 1
"""

from fastapi import FastAPI


app = FastAPI(
    title="Blink Controller API",
    version="1.0",
)


@app.get("/api/v1/health")
async def health():
    """Return basic Pi Controller API health information."""
    return {
        "status": "ok",
        "controller": "blink-controller",
        "api_version": "1",
    }
"""
controller_api.py

Blink Management System - Pi Controller API

Provides the network interface between the Raspberry Pi Blink Controller
and the Windows Management Console.

API Version: 1
"""

from fastapi import FastAPI


def create_app(controller):
    """Create the Controller API around an existing BlinkController."""

    app = FastAPI(
        title="Blink Controller API",
        version="1.0",
    )

    @app.get("/api/v1/health")
    async def health():
        """Return Pi Controller and Blink connection health."""

        connected = controller.blink is not None

        if connected:
            camera_count = len(controller.blink.cameras)
        else:
            camera_count = 0

        return {
            "status": "ok",
            "controller": "blink-controller",
            "api_version": "1",
            "blink_connected": connected,
            "camera_count": camera_count,
        }

    return app
