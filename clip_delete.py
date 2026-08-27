from pathlib import Path
import shutil
import uuid


def stage_clip_for_delete(archive_root, clip):
    """
    Move a clip's local files into a private quarantine directory.

    Returns a dictionary describing the staged files so they can either
    be restored or permanently removed later.
    """

    archive_root = Path(archive_root).resolve()

    quarantine_root = archive_root / ".delete_quarantine"
    quarantine_root.mkdir(parents=True, exist_ok=True)

    quarantine_dir = (
        quarantine_root
        / f"{clip['id']}-{uuid.uuid4().hex}"
    )

    quarantine_dir.mkdir()

    staged_files = []

    video_name = clip.get("filename")

    candidates = [
        (
            "video",
            str(Path("clips") / video_name)
            if video_name
            else None,
        ),
        ("sidecar", clip.get("sidecar_path")),
        ("thumbnail", clip.get("thumbnail_path")),
    ]

    if not video_name:
        raise ValueError("Clip has no video filename")

    video_source = (
        archive_root / "clips" / video_name
    ).resolve()

    if not video_source.is_file():
        raise FileNotFoundError(
            f"Clip video is missing: {video_name}"
        )

    try:
        for file_type, relative_name in candidates:

            if not relative_name:
                continue

            source = (archive_root / relative_name).resolve()

            # Safety: every source must remain beneath archive_root.
            if archive_root not in source.parents:
                raise ValueError(
                    f"{file_type} path escapes archive root: {relative_name}"
                )

            if not source.is_file():
                continue

            destination = quarantine_dir / source.name

            shutil.move(str(source), str(destination))

            staged_files.append(
                {
                    "type": file_type,
                    "source": str(source),
                    "quarantine": str(destination),
                }
            )

        return {
            "catalog_id": clip["id"],
            "blink_media_id": clip.get("blink_media_id"),
            "quarantine_dir": str(quarantine_dir),
            "files": staged_files,
        }

    except Exception:

        # Compensating rollback if staging itself fails partway through.
        for staged in reversed(staged_files):

            quarantine_path = Path(staged["quarantine"])
            source_path = Path(staged["source"])

            if quarantine_path.is_file():
                source_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                shutil.move(
                    str(quarantine_path),
                    str(source_path),
                )

        if quarantine_dir.exists():
            shutil.rmtree(
                quarantine_dir,
                ignore_errors=True,
            )

        raise

def restore_staged_clip(stage):
    """
    Restore all quarantined files to their original locations.

    Raises an exception rather than overwriting an unexpected file.
    """

    staged_files = stage.get("files", [])

    # Verify the entire restore can succeed before moving any file.
    for staged in staged_files:

        quarantine_path = Path(staged["quarantine"])
        source_path = Path(staged["source"])

        if quarantine_path.is_file() and source_path.exists():
            raise FileExistsError(
                f"Cannot restore because destination already exists: "
                f"{source_path}"
            )

    for staged in reversed(staged_files):

        quarantine_path = Path(staged["quarantine"])
        source_path = Path(staged["source"])

        if not quarantine_path.is_file():
            continue

        source_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.move(
            str(quarantine_path),
            str(source_path),
        )

    quarantine_dir = Path(stage["quarantine_dir"])

    if quarantine_dir.exists():
        shutil.rmtree(quarantine_dir)

    return True
