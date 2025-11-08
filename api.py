import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.responses import Response

import psycopg2
from psycopg2.extras import Json

from count_people import marcar_pessoas, _db_connect_from_env, _db_ensure_table
import hashlib


app = FastAPI(title="People Counter API", version="1.0")


def _ensure_db():
    conn = _db_connect_from_env()
    if conn is None:
        return None
    _db_ensure_table(conn)
    return conn


def _compute_hash(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


@app.post("/process", summary="Process image and return annotated image")
async def process_image(
    file: UploadFile = File(...),
    mode: str = Query("seg", enum=["seg", "bbox"]),
    conf: float = Query(0.25, ge=0.0, le=1.0),
):
    # Read file bytes
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # DB connection (opcional). Se não houver DB configurado, apenas processa.
    conn = _ensure_db()

    # Check dedup by hash (somente se DB disponível)
    h = _compute_hash(content)
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute("SELECT id, output_image, metadata FROM images WHERE hash = %s LIMIT 1;", [h])
            row = cur.fetchone()
            if row:
                img_id, output_bytes, meta = row
                # meta pode conter a contagem salva
                count_val = None
                try:
                    if isinstance(meta, dict):
                        count_val = meta.get("count")
                except Exception:
                    count_val = None
                headers = {
                    "X-Image-Id": str(img_id),
                    "X-Duplicate": "true",
                    "X-Count": str(count_val) if count_val is not None else "",
                    "Content-Type": "image/jpeg",
                }
                return Response(content=bytes(output_bytes), media_type="image/jpeg", headers=headers)

    # Not a duplicate — save temp input and process
    suffix = Path(file.filename or "uploaded.jpg").suffix or ".jpg"
    with tempfile.TemporaryDirectory() as td:
        tmp_in = Path(td) / f"input{suffix}"
        tmp_out_dir = Path(td) / "out"
        tmp_out_dir.mkdir(parents=True, exist_ok=True)
        with open(tmp_in, "wb") as f:
            f.write(content)

        # Device selection (API runs on CPU by default)
        device = os.getenv("API_DEVICE", "cpu")
        res = marcar_pessoas(
            input_image=tmp_in,
            output_dir=tmp_out_dir,
            mode=mode,
            conf=conf,
            thickness=3,
            show_label=True,
            device=device,
            export_csv=False,
        )

        out_path = Path(res["output_image"])
        if not out_path.exists():
            raise HTTPException(status_code=500, detail="Failed to generate output image")
        out_bytes = out_path.read_bytes()

        # Store in DB (somente se DB disponível)
        img_id = None
        if conn is not None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO images (input_filename, output_filename, metadata, input_image, output_image, hash)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (hash) DO NOTHING
                    RETURNING id;
                    """,
                    [
                        Path(file.filename or "uploaded.jpg").name,
                        out_path.name,
                        Json({k: v for k, v in res.items() if k != "detections"}),
                        psycopg2.Binary(content),
                        psycopg2.Binary(out_bytes),
                        h,
                    ],
                )
                row = cur.fetchone()
                if row and row[0]:
                    img_id = row[0]
                else:
                    cur.execute("SELECT id FROM images WHERE hash = %s LIMIT 1;", [h])
                    r2 = cur.fetchone()
                    img_id = r2[0] if r2 else None

    headers = {
        "X-Image-Id": str(img_id) if img_id else "",
        "X-Duplicate": "false",
        "X-Count": str(res.get("count", "")),
        "Content-Type": "image/jpeg",
    }
    return Response(content=out_bytes, media_type="image/jpeg", headers=headers)


@app.get("/images/{image_id}", summary="Fetch processed image by id")
def get_image(image_id: int):
    conn = _ensure_db()
    with conn.cursor() as cur:
        cur.execute("SELECT output_image FROM images WHERE id = %s;", [image_id])
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Image not found")
        return Response(content=bytes(row[0]), media_type="image/jpeg")

@app.get("/images/list", summary="List all processed images")
def list_images():
    conn = _ensure_db()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, input_filename, output_filename, metadata, created_at
            FROM images
            ORDER BY id DESC;
        """)
        rows = cur.fetchall()
        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "input_filename": r[1],
                "output_filename": r[2],
                "metadata": r[3],
                "created_at": r[4].isoformat(),
            })
        return results
