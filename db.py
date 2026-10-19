"""
db.py - MongoDB connection (PyMongo) and a small output helper.

Set MONGO_URI to use Atlas or a non-default host, e.g.
    export MONGO_URI="mongodb://localhost:27017"
"""
import json
import os

from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "lifelink_db")


def get_db():
    """Return the database handle. tz_aware=True so dates come back as UTC-aware."""
    client = MongoClient(MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")          # fail fast if the server is not running
    return client[DB_NAME]


def show(title, data):
    """Print a titled result: a list of documents, one document, or a scalar."""
    print(f"\n--- {title} ---")
    if isinstance(data, list):
        if not data:
            print("(no documents)")
        for doc in data:
            print(json.dumps(doc, default=str))
    elif isinstance(data, dict):
        print(json.dumps(data, default=str, indent=2))
    else:
        print(data)
