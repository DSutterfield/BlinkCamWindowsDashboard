-- Blink Controller Catalog
-- Schema Version 1
--
-- Paths are stored relative to /home/dan/BlinkDVR.
-- The database catalogs files; it does not contain MP4,
-- JSON sidecar, or thumbnail image data.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS schema_info (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version  INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_info (id, schema_version)
VALUES (1, 1);

CREATE TABLE IF NOT EXISTS systems (
    id                  INTEGER PRIMARY KEY,
    blink_system_id     TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    raw_name            TEXT,

    active              INTEGER NOT NULL DEFAULT 1
                        CHECK (active IN (0, 1)),

    first_seen_at       TEXT,
    last_seen_at        TEXT,
    removed_at          TEXT,

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS devices (
    id                  INTEGER PRIMARY KEY,
    blink_device_id     TEXT NOT NULL,
    system_id           INTEGER,

    entity_type         TEXT NOT NULL DEFAULT 'camera',

    name                TEXT NOT NULL,
    raw_name            TEXT,

    class_name          TEXT,
    device_type         TEXT,
    raw_type            TEXT,

    serial              TEXT,
    firmware_version    TEXT,

    active              INTEGER NOT NULL DEFAULT 1
                        CHECK (active IN (0, 1)),

    first_seen_at       TEXT,
    last_seen_at        TEXT,
    removed_at          TEXT,

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (system_id)
        REFERENCES systems(id)
        ON DELETE SET NULL,

    UNIQUE (blink_device_id, entity_type)
);

CREATE TABLE IF NOT EXISTS clips (
    id                      INTEGER PRIMARY KEY,

    blink_media_id          TEXT UNIQUE,

    metadata_status         TEXT NOT NULL DEFAULT 'matched'
                            CHECK (metadata_status IN ('matched', 'local_only')),

    device_id               INTEGER,
    system_id               INTEGER,

    device_name_snapshot    TEXT,
    system_name_snapshot    TEXT,

    filename                TEXT NOT NULL,
    video_path              TEXT NOT NULL UNIQUE,
    sidecar_path            TEXT UNIQUE,
    metadata_source_path    TEXT,
    thumbnail_path          TEXT,
    thumbnail_cloud_url     TEXT,

    file_size_bytes         INTEGER,

    captured_at             TEXT NOT NULL,
    blink_updated_at        TEXT,
    time_zone               TEXT,

    watched                 INTEGER
                            CHECK (
                                watched IS NULL
                                OR watched IN (0, 1)
                            ),

    source                  TEXT,
    media_type              TEXT,

    trigger_type            TEXT,
    cv_detection_json       TEXT,

    duration_ms             INTEGER,

    local_present           INTEGER NOT NULL DEFAULT 1
                            CHECK (local_present IN (0, 1)),

    cloud_present           INTEGER
                            CHECK (
                                cloud_present IS NULL
                                OR cloud_present IN (0, 1)
                            ),

    imported_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    catalog_updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (device_id)
        REFERENCES devices(id)
        ON DELETE SET NULL,

    FOREIGN KEY (system_id)
        REFERENCES systems(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_devices_system
    ON devices(system_id);

CREATE INDEX IF NOT EXISTS idx_devices_name
    ON devices(name);

CREATE INDEX IF NOT EXISTS idx_clips_captured_at
    ON clips(captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_clips_device
    ON clips(device_id);

CREATE INDEX IF NOT EXISTS idx_clips_system
    ON clips(system_id);

CREATE INDEX IF NOT EXISTS idx_clips_watched
    ON clips(watched);

CREATE INDEX IF NOT EXISTS idx_clips_device_time
    ON clips(device_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_clips_system_time
    ON clips(system_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_clips_trigger
    ON clips(trigger_type);
