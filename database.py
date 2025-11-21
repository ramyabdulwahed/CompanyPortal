import psycopg
import os
from flask import g

"""
Gets and returns database connection
"""
def get_database():
    if 'db' not in g:
        url = os.environ.get('DATABASE_URL')

        if not url:
            raise RuntimeError("DATABASE_URL env var not found")
        
        g.db = psycopg.connect(url)

    return g.db

"""
Closes database connection
"""
def close_database(e=None): 
    db = g.pop('db', None) 
    if db is not None:
        db.close()

"""
Links app to close database
"""
def init_app(app):
    app.teardown_appcontext(close_database)