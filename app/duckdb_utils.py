import duckdb

def get_connection():
    return duckdb.connect('/mnt/data/forensic.duckdb')




