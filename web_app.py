"""
Blink DVR Web Dashboard
Run: python web_app.py
Access: http://localhost:5000 (or http://<your-pc-ip>:5000 on LAN)
"""
import atexit
import asyncio
from camera_model import build_camera_records
import configparser
import json
import logging
import motion_tracker


from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from aiohttp import ClientSession
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from liveview_bridge import LiveViewBridge
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

logging.getLogger("blinkpy").setLevel(logging.WARNING)

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config" / "settings.ini"
CREDS_PATH = ROOT / "config" / "credentials.json"

THUMBS_DIR = ROOT / "static" / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

# 2026-08-13 - Dan/Sage:
# Cache recorded-clip thumbnails locally after their first retrieval
# from Blink.  This prevents repeated cloud requests when the clip list
# is refreshed or reopened.
CLIP_THUMBS_DIR = ROOT / "static" / "clip_thumbs"
CLIP_THUMBS_DIR.mkdir(parents=True, exist_ok=True)

config = configparser.ConfigParser()
config.read(CONFIG_PATH)
CLIPS_DIR = Path(config["download"]["output_dir"])

app = Flask(__name__)
blink_lock = Lock()

# 2026-08-04 - Dan/Sage:
# Keep one live-view bridge alive for the Dashboard process. The bridge
# owns its own asyncio loop and permits one active camera stream at a time.
liveview_bridge = LiveViewBridge()
atexit.register(liveview_bridge.shutdown)


def run_async(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def with_blink(action_coro):
    saved = json.loads(CREDS_PATH.read_text())
    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()
        return await action_coro(blink)


def thumb_filename(camera_name):
    """Map a camera name to a safe filename for its thumbnail."""
    safe = "".join(c if c.isalnum() else "_" for c in camera_name)
    return f"{safe}.jpg"


# --- Routes ---------------------------------------------------------------
@app.route("/api/active_motion")
def api_active_motion():
    """Return cameras currently in active motion state."""
    return jsonify(motion_tracker.get_active_cameras())

@app.route("/")
def index():
    return render_template("index.html")


# --- Live-view routes -----------------------------------------------------
@app.route("/api/liveview/start", methods=["POST"])
def api_liveview_start():
    """Start one camera's live view and wait for the first decoded frame."""
    payload = request.get_json(silent=True) or {}
    camera_name = str(payload.get("name", "")).strip()

    if not camera_name:
        return jsonify({
            "ok": False,
            "error": "A camera name is required.",
        }), 400

    try:
        result = liveview_bridge.start(camera_name)
        return jsonify(result)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@app.route("/api/liveview/stream")
def api_liveview_stream():
    """Publish the active camera as a browser-compatible MJPEG stream."""
    status = liveview_bridge.status()

    # 2026-08-04 - Dan/Sage:
    # Permit the browser to receive the final decoded frame when Blink's
    # short live-view feed ends before the MJPEG request reaches Flask.
    if not status["active"] and status["frames"] == 0:
        return jsonify({
            "ok": False,
            "error": status["error"] or "No live-view frames are available.",
        }), 409

    return Response(
        liveview_bridge.iter_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.route("/api/liveview/status")
def api_liveview_status():
    """Return the current live-view camera, frame count, and error state."""
    return jsonify(liveview_bridge.status())


@app.route("/api/liveview/stop", methods=["POST"])
def api_liveview_stop():
    """Stop the active live-view stream without closing the Dashboard."""
    try:
        liveview_bridge.stop()
        return jsonify({
            "ok": True,
            "active": False,
        })
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@app.route("/api/cameras")
def api_cameras():
    async def fetch(blink):
        sync_modules = getattr(blink, "sync", {}) or {}
        system_armed = any(sm.arm for sm in sync_modules.values())

        cameras = build_camera_records(blink)

        # 2026-08-01 - Dan/Sage:
        # Add web-specific media links without duplicating normalized camera
        # status or capability fields at the top level of the API record.
        for camera in cameras:
            camera["media"] = {
                "thumbnail_url": (
                f"/static/thumbs/{thumb_filename(camera['raw_name'])}"
            )
        }

        return {
            "system_armed": system_armed,
            "cameras": cameras,
        }

    with blink_lock:
        return jsonify(run_async(with_blink(fetch)))


@app.route("/api/refresh_thumbnails", methods=["POST"])
def api_refresh_thumbnails():
    """Pull fresh thumbnails for every camera and save to static/thumbs/."""
    async def refresh(blink):
        results = {}
        for name, cam in blink.cameras.items():
            try:
                await cam.snap_picture()      # tell Blink to capture a fresh thumb
                await asyncio.sleep(2)         # give it a moment to upload
                await cam.get_thumbnail()      # pull the URL
                dest = THUMBS_DIR / thumb_filename(name)
                await cam.image_to_file(str(dest))
                results[name] = "ok"
            except Exception as e:
                results[name] = f"error: {e}"
        return results

    with blink_lock:
        return jsonify(run_async(with_blink(refresh)))


@app.route("/api/refresh_thumbnail/<path:name>", methods=["POST"])
def api_refresh_one_thumbnail(name):
    """Refresh a single camera's thumbnail. Faster than refreshing all."""
    async def refresh(blink):
        if name not in blink.cameras:
            return {"ok": False, "error": "Camera not found"}
        cam = blink.cameras[name]
        try:
            await cam.snap_picture()
            await asyncio.sleep(2)
            await cam.get_thumbnail()
            dest = THUMBS_DIR / thumb_filename(name)
            await cam.image_to_file(str(dest))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    with blink_lock:
        return jsonify(run_async(with_blink(refresh)))

@app.route("/api/clip_thumbnail/<path:filename>")
def api_clip_thumbnail(filename):
    """Return a locally cached recorded-clip thumbnail."""

    # 2026-08-13 - Dan/Sage:
    # The browser must never wait while this route contacts Blink.
    # Blink thumbnail retrieval is handled separately by the DVR poller.
    # If a thumbnail has not been cached yet, return immediately.
    clips_root = CLIPS_DIR.resolve()
    mp4 = (CLIPS_DIR / filename).resolve()

    if mp4.parent != clips_root:
        return Response(status=400)

    cache_name = f"{mp4.stem}.jpg"
    cache_path = CLIP_THUMBS_DIR / cache_name

    if not cache_path.exists():
        return Response(status=404)

    return send_from_directory(
        CLIP_THUMBS_DIR,
        cache_name,
        mimetype="image/jpeg",
    )



@app.route("/api/arm", methods=["POST"])
def api_arm():
    state = request.json.get("armed", True)

    async def do_arm(blink):
        sync_modules = getattr(blink, "sync", {}) or {}
        for sm in sync_modules.values():
            try:
                await sm.async_arm(state)
            except Exception:
                pass
        return {"ok": True, "armed": state}

    with blink_lock:
        return jsonify(run_async(with_blink(do_arm)))


@app.route("/api/camera/motion", methods=["POST"])
def api_camera_motion():
    name = request.json.get("name")
    enable = request.json.get("enable", True)

    async def do_toggle(blink):
        if name not in blink.cameras:
            return {"ok": False, "error": f"Camera not found: {name}"}
        cam = blink.cameras[name]
        try:
            await cam.async_arm(enable)
        except Exception:
            pass
        return {"ok": True, "name": name, "enabled": enable}

    with blink_lock:
        return jsonify(run_async(with_blink(do_toggle)))


@app.route("/api/clips")
def api_clips():
    """List every downloaded MP4 with its actual recording time.

    Developer note — 2026-08-02, Dan and Sage:
    The original viewer sorted clips by the MP4 file's modified time.
    That value normally represents when the file was downloaded, not when
    the camera recorded it.

    Recording time is now obtained in this order:
        1. Blink sidecar metadata created_at
        2. Timestamp encoded in the BlinkPy filename
        3. File modified time as a last-resort fallback

    The former 200-clip limit was also removed. Pagination can be added
    later if the collection becomes large enough to require it.
    """
    from metadata_helper import filename_to_timestamp, read_sidecar

    if not CLIPS_DIR.exists():
        return jsonify([])

    clips = []

    for mp4 in CLIPS_DIR.glob("*.mp4"):
        stat = mp4.stat()
        sidecar = read_sidecar(mp4)

        recorded_dt = None
        recorded_source = None

        # Best source: the timestamp returned by Blink for the media event.
        if sidecar:
            created_at = sidecar.get("created_at")

            if created_at:
                try:
                    recorded_dt = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )

                    if recorded_dt.tzinfo is None:
                        recorded_dt = recorded_dt.replace(
                            tzinfo=timezone.utc
                        )

                    recorded_dt = recorded_dt.astimezone(timezone.utc)
                    recorded_source = "metadata"
                except (TypeError, ValueError):
                    recorded_dt = None

        # Second choice: timestamp encoded in the downloaded filename.
        if recorded_dt is None:
            filename_dt = filename_to_timestamp(mp4.name)

            if filename_dt is not None:
                recorded_dt = filename_dt.replace(tzinfo=timezone.utc)
                recorded_source = "filename"

        # Last resort: when the MP4 file was written to local storage.
        if recorded_dt is None:
            recorded_dt = datetime.fromtimestamp(
                stat.st_mtime,
                tz=timezone.utc,
            )
            recorded_source = "file_modified"

        clip_data = {
            "filename": mp4.name,
            "camera_name": "Unknown camera",
            "network_name": "Unknown system",
            "size_mb": round(stat.st_size / 1_000_000, 2),

            # Actual camera recording time whenever available.
            "recorded_at": recorded_dt.isoformat(),
            "recorded_source": recorded_source,

            # Retained separately for diagnostics and file management.
            "modified": datetime.fromtimestamp(
                stat.st_mtime,
                tz=timezone.utc,
            ).isoformat(),

            "source": None,
            "cv_detection": [],
            "watched": None,
        }

        if sidecar:
            clip_data["camera_name"] = (
                sidecar.get("device_name")
                or "Unknown camera"
            )

            # 2026-08-13 - Dan/Sage:
            # Supply the Blink system/network name to the Recorded Clips
            # display for the new three-column clip layout.
            clip_data["network_name"] = (
                sidecar.get("network_name")
                or "Unknown system"
            )
           
            clip_data["source"] = sidecar.get("source")
            clip_data["cv_detection"] = sidecar.get(
                "cv_detection",
                [],
            )
            clip_data["watched"] = sidecar.get("watched")

        clips.append(clip_data)

    # The API defaults to newest recording first. The browser will soon
    # allow the operator to reverse this order without another API request.
    clips.sort(
        key=lambda clip: clip["recorded_at"],
        reverse=True,
    )

    return jsonify(clips)


@app.route("/clips/<path:filename>")
def serve_clip(filename):
    return send_from_directory(CLIPS_DIR, filename)

# 2026-08-11 - Dan/Sage:
# Mark one Blink media event as viewed. The Blink event ID is obtained
# from the clip's sidecar so the browser does not have to know Blink IDs.
@app.route("/api/clips/mark-viewed", methods=["POST"])
def api_mark_clip_viewed():
    from metadata_helper import metadata_path_for, read_sidecar

    data = request.get_json(silent=True) or {}
    filename = data.get("filename")

    if not filename or filename != Path(filename).name:
        return jsonify({"ok": False, "error": "Invalid filename"}), 400

    if not filename.lower().endswith(".mp4"):
        return jsonify({"ok": False, "error": "Not a clip file"}), 400

    clips_dir = CLIPS_DIR.resolve()
    target = (clips_dir / filename).resolve()

    if clips_dir != target.parent:
        return jsonify({"ok": False, "error": "Path escapes clips directory"}), 400

    if not target.is_file():
        return jsonify({"ok": False, "error": "Clip not found"}), 404

    sidecar = read_sidecar(target)

    if not sidecar:
        return jsonify({"ok": False, "error": "Clip metadata not found"}), 404

    event_id = sidecar.get("id")

    if event_id is None:
        return jsonify({"ok": False, "error": "Blink event ID not found"}), 400

    async def mark_viewed(blink):
        url = (
            f"{blink.urls.base_url}/api/v4/accounts/{blink.account_id}"
            f"/media/mark_as_viewed"
        )

        headers = dict(blink.auth.header)
        headers["Content-Type"] = "application/json"

        body = {
            "media_list": [event_id]
        }

        await blink.auth.query(
            url=url,
            data=json.dumps(body),
            headers=headers,
            reqtype="post",
            json_resp=False,
        )

        return {"ok": True}

    try:
        with blink_lock:
            result = run_async(with_blink(mark_viewed))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    # Blink accepted the request. Update our local sidecar immediately.
    sidecar["watched"] = True

    try:
        metadata_path_for(target).write_text(
            json.dumps(sidecar, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        return jsonify({
            "ok": False,
            "error": f"Blink was updated, but the sidecar update failed: {e}",
        }), 500

    return jsonify(result)

@app.route("/api/clips/mark-all-viewed", methods=["POST"])
def api_mark_all_clips_viewed():
    """Mark every locally known unreviewed Blink clip as viewed."""

    # 2026-08-14 - Dan/Sage:
    # "Mark all" applies to the complete local clip collection,
    # independent of the Dashboard's current search/date filters.
    # Only sidecars explicitly reporting watched=False are included.
    from metadata_helper import metadata_path_for, read_sidecar

    pending = []

    for mp4 in CLIPS_DIR.glob("*.mp4"):
        sidecar = read_sidecar(mp4)

        if not sidecar:
            continue

        if sidecar.get("watched") is not False:
            continue

        event_id = sidecar.get("id")

        if event_id is None:
            continue

        pending.append((mp4, sidecar, event_id))

    if not pending:
        return jsonify({
            "ok": True,
            "marked": 0,
        })

    # Keep each request reasonably small rather than sending hundreds
    # of Blink event IDs in one POST.
    batch_size = 100
    marked = 0

    async def mark_batch(blink, event_ids):
        url = (
            f"{blink.urls.base_url}/api/v4/accounts/{blink.account_id}"
            f"/media/mark_as_viewed"
        )

        headers = dict(blink.auth.header)
        headers["Content-Type"] = "application/json"

        body = {
            "media_list": event_ids
        }

        response = await blink.auth.query(
            url=url,
            data=json.dumps(body),
            headers=headers,
            reqtype="post",
            json_resp=False,
        )

        if response is None:
            raise RuntimeError(
                "Blink did not return a response."
            )

        try:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"Blink returned HTTP {response.status}."
                )
        finally:
            response.release()

    try:
        with blink_lock:
            for start in range(0, len(pending), batch_size):
                batch = pending[start:start + batch_size]
                event_ids = [
                    event_id
                    for _, _, event_id in batch
                ]

                run_async(
                    with_blink(
                        lambda blink, ids=event_ids:
                            mark_batch(blink, ids)
                    )
                )

                # Blink accepted this batch. Update only those local
                # sidecars that were included in the successful POST.
                for mp4, sidecar, _ in batch:
                    sidecar["watched"] = True

                    metadata_path_for(mp4).write_text(
                        json.dumps(sidecar, indent=2),
                        encoding="utf-8",
                    )

                    marked += 1

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "marked": marked,
        }), 500

    return jsonify({
        "ok": True,
        "marked": marked,
    })

@app.route("/api/clips/delete", methods=["POST"])
def api_delete_clip():
    """Delete a single downloaded clip (and its sidecar/thumbnail) from local disk.

    This only removes the local copy. If the clip is still within Blink's cloud
    retention window, blink_dvr.py may re-download it on its next poll.
    """
    filename = (request.json or {}).get("filename", "")

    # --- Safety: only a bare filename, no path components ---
    if not filename or filename != Path(filename).name:
        return jsonify({"ok": False, "error": "Invalid filename"}), 400
    if not filename.lower().endswith(".mp4"):
        return jsonify({"ok": False, "error": "Not a clip file"}), 400

    clips_dir = CLIPS_DIR.resolve()
    target = (clips_dir / filename).resolve()

    # --- Safety: resolved path must still live inside CLIPS_DIR ---
    if clips_dir != target.parent:
        return jsonify({"ok": False, "error": "Path escapes clips directory"}), 400
    if not target.is_file():
        return jsonify({"ok": False, "error": "File not found"}), 404

    try:
        target.unlink()
        # Remove sidecar metadata + any cached thumbnail alongside it.
        # Covers both 'clip.json' and 'clip.mp4.json' naming conventions.
        for sidecar in (target.with_suffix(".json"),
                        target.with_suffix(".mp4.json"),
                        target.with_suffix(".jpg")):
            if sidecar.is_file():
                sidecar.unlink()
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "filename": filename})


if __name__ == "__main__":
    print("Blink DVR Web starting on http://0.0.0.0:5000")
    print("Access from this PC: http://localhost:5000")
    print("Access from phones/tablets on same WiFi: http://<your-pc-ip>:5000")
    
    motion_tracker.start_background_thread()
    print("Motion tracker started (polls Blink every 10 sec)")
    
    
    app.run(host="0.0.0.0", port=5000, debug=False)