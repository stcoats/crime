from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import duckdb
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

@app.get("/")
def serve_index():
    return FileResponse("app/static/index.html")

# Initialize the connection
def get_connection():
    return duckdb.connect('/mnt/data/forensic.duckdb', read_only=True)

con = get_connection()

@app.get("/data")
def get_paginated_data(
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=1000),
    text: str = Query(""),
    sort: str = Query("ID"),
    direction: str = Query("asc")
):
    allowed_cols = ["ID", "playlist", "title", "timing", "transcript", "pos_tags", "audio"]
    if sort not in allowed_cols:
        sort = "ID"
    if direction not in ["asc", "desc"]:
        direction = "asc"

    text_clean = text.strip().strip('"“”\'')  # remove quotes/smartquotes
    where_clause = ""

    if text_clean:
        # Convert "can can" => can\s+can, then add word boundaries manually
        phrase = re.sub(r'\s+', r'\\s+', text_clean)
        pattern = f'(^|\\W){phrase}(\\W|$)'

        # Add search condition for both text and pos_tags
        where_clause = f"""
        WHERE regexp_matches(transcript, '{pattern}', 'i')
           OR regexp_matches(pos_tags, '{pattern}', 'i')
        """

    offset = (page - 1) * size

    count_query = f"SELECT COUNT(*) FROM forensic_data {where_clause}"
    try:
        total = con.execute(count_query).fetchone()[0]

        query = f"""
        SELECT ID, playlist, title, timing, transcript, pos_tags, audio
        FROM forensic_data
        {where_clause}
        ORDER BY {sort} {direction}
        LIMIT {size} OFFSET {offset}
        """
        df = con.execute(query).df()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data query error: {e}")

    return {"total": total, "data": df.to_dict(orient="records")}

@app.get("/audio/{id}")
def get_audio(id: str):
    try:
        row = con.execute("SELECT audio FROM forensic_data WHERE ID = ?", [id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Audio not found")
        return {"audio_url": row[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio lookup error: {e}")
