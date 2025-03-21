from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3
import pandas as pd
import re

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
    text: str = Query("")
):
    offset = (page - 1) * size
    text_clean = text.strip().strip()
    where_clause = ""

    if text_clean:
        match_expr = re.sub(r'\s+', ' ', text_clean)
        where_clause = f"""
        WHERE rowid IN (
            SELECT rowid FROM forensic_data_fts
            WHERE forensic_data_fts MATCH {repr(match_expr)}
        )
        """

    try:
        count_query = f"SELECT COUNT(*) FROM forensic_data {where_clause}"
        total = con.execute(count_query).fetchone()[0]

        query = f"""
        SELECT id, playlist, title, timing, transcript, pos_tags, audio
        FROM forensic_data
        {where_clause}
        LIMIT {size} OFFSET {offset}
        """
        df = pd.read_sql_query(query, con)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data query error: {e}")

    return {"total": total, "data": df.to_dict(orient="records")}

@app.get("/audio/{id}")
def get_audio(id: str):
    try:
        row = con.execute("SELECT audio FROM forensic_data WHERE id = ?", [id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Audio not found")
        return {"audio_url": row[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio lookup error: {e}")
