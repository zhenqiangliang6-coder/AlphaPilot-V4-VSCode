# sqlite_adapter.py

import sqlite3
from contextlib import closing

class SQLiteAdapter:
    def __init__(self, db_file):
        self.db_file = db_file

    def connect(self):
        return sqlite3.connect(self.db_file)

    def execute_query(self, query, params=None):
        with closing(self.connect()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute(query, params or [])
                conn.commit()
                return cursor.fetchall()

    def fetch_all(self, table):
        query = f"SELECT * FROM {table}"
        return self.execute_query(query)

    def fetch_one(self, table, id):
        query = f"SELECT * FROM {table} WHERE id = ?"
        return self.execute_query(query, (id,))

    def insert(self, table, columns, values):
        placeholders = ', '.join('?' * len(values))
        query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        self.execute_query(query, values)

    def update(self, table, columns, values, id):
        set_clause = ', '.join(f"{col} = ?" for col in columns)
        query = f"UPDATE {table} SET {set_clause} WHERE id = ?"
        self.execute_query(query, values + [id])

    def delete(self, table, id):
        query = f"DELETE FROM {table} WHERE id = ?"
        self.execute_query(query, (id,))