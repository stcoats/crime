import duckdb

def get_connection():
    return duckdb.connect("/tmp/forensic.duckdb")



