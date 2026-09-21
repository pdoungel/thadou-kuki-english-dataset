from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "studio.db"
FRONTEND = APP_DIR / "frontend" / "index.html"

DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Thadou-Kuki Language AI Studio",
    version="0.1.0",
    description="Dataset curation, review and bilingual translation-development workspace for Thadou-Kuki ↔ English.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    return " ".join(text.split()).strip()


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref TEXT,
                thadou TEXT NOT NULL,
                english TEXT NOT NULL,
                source_id TEXT NOT NULL DEFAULT 'unknown',
                split TEXT NOT NULL DEFAULT 'unassigned',
                status TEXT NOT NULL DEFAULT 'unreviewed',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(thadou, english, source_id)
            );

            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                license TEXT NOT NULL DEFAULT '',
                rights_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                canonical_url TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_segments_status ON segments(status);
            CREATE INDEX IF NOT EXISTS idx_segments_split ON segments(split);
            CREATE INDEX IF NOT EXISTS idx_segments_source ON segments(source_id);
        """
        )
    sync_metadata_sources()


def sync_metadata_sources() -> None:
    metadata = ROOT / "metadata" / "sources.json"
    if not metadata.exists():
        return
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    records = payload if isinstance(payload, list) else payload.get("sources", [])
    with connect() as con:
        for item in records:
            source_id = item.get("source_id") or item.get("id")
            if not source_id:
                continue
            con.execute(
                """INSERT INTO sources(source_id,title,provider,license,rights_status,canonical_url,notes)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(source_id) DO UPDATE SET
                     title=excluded.title, provider=excluded.provider, license=excluded.license,
                     rights_status=excluded.rights_status, canonical_url=excluded.canonical_url,
                     notes=excluded.notes""",
                (source_id, item.get("title", ""), item.get("provider", item.get("publisher", "")),
                 item.get("license", ""), item.get("rights_status", item.get("rights", "UNKNOWN")),
                 item.get("url", item.get("canonical_url", "")), item.get("notes", "")),
            )


class SegmentUpdate(BaseModel):
    thadou: str = Field(min_length=1)
    english: str = Field(min_length=1)
    status: str = Field(default="unreviewed")
    notes: str = Field(default="")
    split: str = Field(default="unassigned")


class ImportRequest(BaseModel):
    path: str = "out/parallel.tsv"
    source_id: str = "ebible-chongthu"


class Source(BaseModel):
    source_id: str
    title: str
    provider: str = ""
    license: str = ""
    rights_status: str = "UNKNOWN"
    canonical_url: str = ""
    notes: str = ""


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def home():
    return FileResponse(FRONTEND)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": app.title, "version": app.version}


@app.get("/api/stats")
def stats():
    with connect() as con:
        total = con.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        reviewed = con.execute(
            "SELECT COUNT(*) FROM segments WHERE status IN ('approved','corrected')"
        ).fetchone()[0]
        rejected = con.execute("SELECT COUNT(*) FROM segments WHERE status='rejected'").fetchone()[0]
        pending = con.execute(
            "SELECT COUNT(*) FROM segments WHERE status='unreviewed'"
        ).fetchone()[0]
        sources = con.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        return {
            "segments": total,
            "reviewed": reviewed,
            "pending": pending,
            "rejected": rejected,
            "sources": sources,
        }


@app.get("/api/segments")
def list_segments(
    q: str = "",
    status: str = "",
    source_id: str = "",
    direction: str = "thadou_to_english",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    # Direction controls which side is emphasized by the search UI; both fields are searched.
    del direction
    clauses, params = [], []
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(thadou LIKE ? OR english LIKE ? OR ref LIKE ?)")
        params.extend([like, like, like])
    if status:
        clauses.append("status = ?")
        params.append(status)
    if source_id:
        clauses.append("source_id = ?")
        params.append(source_id)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as con:
        rows = con.execute(
            f"""SELECT id, ref, thadou, english, source_id, split, status, notes,
                       created_at, updated_at
                FROM segments{where}
                ORDER BY id
                LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
        total = con.execute(f"SELECT COUNT(*) FROM segments{where}", params).fetchone()[0]
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@app.get("/api/segments/{segment_id}")
def get_segment(segment_id: int):
    with connect() as con:
        row = con.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Segment not found")
    return dict(row)


@app.put("/api/segments/{segment_id}")
def update_segment(segment_id: int, payload: SegmentUpdate):
    thadou, english = norm(payload.thadou), norm(payload.english)
    if not thadou or not english:
        raise HTTPException(400, "Both Thadou-Kuki and English text are required")
    if payload.status not in {"unreviewed", "approved", "corrected", "rejected"}:
        raise HTTPException(400, "Invalid review status")
    if payload.split not in {"unassigned", "train", "validation", "test"}:
        raise HTTPException(400, "Invalid split")

    with connect() as con:
        cur = con.execute(
            """UPDATE segments
               SET thadou=?, english=?, status=?, notes=?, split=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (thadou, english, payload.status, payload.notes.strip(), payload.split, segment_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Segment not found")
    return get_segment(segment_id)


@app.get("/api/sources")
def list_sources():
    with connect() as con:
        rows = con.execute("SELECT * FROM sources ORDER BY source_id").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/sources")
def upsert_source(source: Source):
    with connect() as con:
        con.execute(
            """INSERT INTO sources(source_id,title,provider,license,rights_status,canonical_url,notes)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET
                 title=excluded.title, provider=excluded.provider, license=excluded.license,
                 rights_status=excluded.rights_status, canonical_url=excluded.canonical_url,
                 notes=excluded.notes""",
            tuple(source.model_dump().values()),
        )
    return source.model_dump()


@app.post("/api/import")
def import_dataset(payload: ImportRequest):
    source_path = (ROOT / payload.path).resolve()
    if ROOT not in source_path.parents and source_path != ROOT:
        raise HTTPException(400, "Import path must stay inside the repository")
    if not source_path.exists():
        raise HTTPException(404, f"File not found: {payload.path}")

    sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    inserted = 0
    duplicates = 0

    with source_path.open("r", encoding="utf-8", newline="") as fh, connect() as con:
        reader = csv.DictReader(fh, delimiter="\t")
        if not reader.fieldnames or "thadou" not in reader.fieldnames or "english" not in reader.fieldnames:
            raise HTTPException(400, "TSV must contain thadou and english columns")
        for row in reader:
            thadou, english = norm(row.get("thadou", "")), norm(row.get("english", ""))
            if not thadou or not english:
                continue
            ref = norm(row.get("ref", ""))
            try:
                con.execute(
                    """INSERT INTO segments(ref,thadou,english,source_id)
                       VALUES(?,?,?,?)""",
                    (ref, thadou, english, payload.source_id),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                duplicates += 1

    return {"source_id": payload.source_id, "path": payload.path, "sha256": sha,
            "inserted": inserted, "duplicates": duplicates}


@app.post("/api/import-existing")
def import_existing():
    return import_dataset(ImportRequest(path="out/parallel.tsv", source_id="ebible-chongthu"))


@app.get("/api/translation-directions")
def translation_directions():
    return [
        {"id": "thadou_to_english", "label": "Thadou-Kuki → English"},
        {"id": "english_to_thadou", "label": "English → Thadou-Kuki"},
    ]


@app.get("/api/export")
def export_reviewed():
    # Export endpoint is intentionally limited to reviewed rows.
    with connect() as con:
        rows = con.execute(
            """SELECT ref, thadou, english, source_id, split, status
               FROM segments WHERE status IN ('approved','corrected')
               ORDER BY id"""
        ).fetchall()
    return {"items": [dict(r) for r in rows], "count": len(rows)}
