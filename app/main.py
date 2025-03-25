from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3
import pandas as pd
import re
import io
import zipfile
import os
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

def get_connection():
    return sqlite3.connect('/mnt/data/forensic.sqlite', check_same_thread=False)

con = get_connection()

@app.get("/")
def serve_index():
    return FileResponse("app/static/index.html")

@app.get("/data")
def get_paginated_data(
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=1000),
    text: str = Query(""),
    playlists: str = Query("")
):
    offset = (page - 1) * size
    text_clean = text.strip()
    where_clauses = []
    query_params = []

    if text_clean:
        match_expr = re.sub(r'\s+', ' ', text_clean)
        where_clauses.append("""
        rowid IN (
            SELECT rowid FROM forensic_data_fts
            WHERE forensic_data_fts MATCH ?
        )
        """)
        query_params.append(match_expr)

    if playlists:
        selected = [p.strip() for p in playlists.split(",") if p.strip()]
        if selected:
            placeholders = ",".join(["?"] * len(selected))
            where_clauses.append(f"playlist IN ({placeholders})")
            query_params.extend(selected)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    try:
        count_query = f"SELECT COUNT(*) FROM forensic_data {where_sql}"
        total = con.execute(count_query, query_params).fetchone()[0]

        query = f"""
        SELECT id, playlist, title, timing, transcript, pos_tags, audio
        FROM forensic_data
        {where_sql}
        LIMIT {size} OFFSET {offset}
        """
        df = pd.read_sql_query(query, con, params=query_params)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data query error: {e}")

    return {"total": total, "data": df.to_dict(orient="records")}

@app.get("/playlists")
def get_playlists():
    try:
        result = con.execute("SELECT DISTINCT playlist FROM forensic_data ORDER BY playlist").fetchall()
        playlists = [row[0] for row in result if row[0]]
        return playlists
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get playlists: {e}")

@app.get("/audio/{id}")
def get_audio(id: str):
    try:
        row = con.execute("SELECT audio FROM forensic_data WHERE id = ?", [id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Audio not found")
        return {"audio_url": row[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio lookup error: {e}")

@app.get("/download/csv")
def download_csv(text: str = Query(""), playlists: str = Query("")):
    try:
        where_clauses = []
        query_params = []

        if text.strip():
            match_expr = re.sub(r'\s+', ' ', text.strip())
            where_clauses.append("""
            rowid IN (
                SELECT rowid FROM forensic_data_fts
                WHERE forensic_data_fts MATCH ?
            )
            """)
            query_params.append(match_expr)

        if playlists:
            selected = [p.strip() for p in playlists.split(",") if p.strip()]
            if selected:
                placeholders = ",".join(["?"] * len(selected))
                where_clauses.append(f"playlist IN ({placeholders})")
                query_params.extend(selected)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        query = f"""
        SELECT id, playlist, title, timing, transcript, pos_tags, audio
        FROM forensic_data
        {where_sql}
        """
        df = pd.read_sql_query(query, con, params=query_params)

        csv_io = io.StringIO()
        df.to_csv(csv_io, index=False)
        csv_io.seek(0)
        return StreamingResponse(iter([csv_io.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=forensic_data.csv"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export CSV: {e}")

@app.get("/download/mp3zip")
def download_mp3_zip(text: str = Query(""), playlists: str = Query("")):
    try:
        where_clauses = []
        query_params = []

        if text.strip():
            match_expr = re.sub(r'\s+', ' ', text.strip())
            where_clauses.append("""
            rowid IN (
                SELECT rowid FROM forensic_data_fts
                WHERE forensic_data_fts MATCH ?
            )
            """)
            query_params.append(match_expr)

        if playlists:
            selected = [p.strip() for p in playlists.split(",") if p.strip()]
            if selected:
                placeholders = ",".join(["?"] * len(selected))
                where_clauses.append(f"playlist IN ({placeholders})")
                query_params.extend(selected)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        query = f"SELECT audio FROM forensic_data {where_sql}"
        df = pd.read_sql_query(query, con, params=query_params)
        audio_urls = df["audio"].dropna().unique()

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for url in audio_urls:
                try:
                    filename = os.path.basename(url.split("?")[0])
                    response = requests.get(url, timeout=10)
                    if response.ok:
                        zipf.writestr(filename, response.content)
                except Exception:
                    continue  # skip failures

        zip_buffer.seek(0)
        return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=forensic_mp3s.zip"})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create ZIP: {e}")
