## Initial architecture observation

`start_blink.bat` launches three independent processes:

1. `blink_dvr.py` polls Blink and downloads camera clips.
2. `web_app.py` provides the local Flask operator interface.
3. The default browser displays the dashboard.

The Python processes do not share memory. Coordination appears to depend on
shared local files/directories and the Blink cloud service.

## Package	Architectural roles

blinkpy	Interface to Blink cloud services
Flask	Local operator interface
aiohttp	Non-blocking network communication
python-dateutil	Time and date calculations

Blink DRS Developer Notes

2026-07-24

Initial Environment

- Repository cloned successfully.
- Git synchronized with origin/master.
- Project uses a Python virtual environment (.venv).
- Application starts with:

    .\.venv\Scripts\python.exe web_app.py

- Flask server listens on:
    http://127.0.0.1:5000

Packages installed today:
- aiohttp
- blinkpy
- flask