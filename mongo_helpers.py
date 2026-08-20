"""
MongoDB Atlas data layer — drop-in replacement for google_sheets_helpers.py.

Every function here has the SAME name and signature as the old Sheets
version, so routes/*.py, cart_utils.py, ai_chat_handler.py etc. don't need
any logic changes — only the import line changes.

Collections (instead of Sheet IDs):
    ADMINS_FILE    = "admins"
    CUSTOMERS_FILE = "customers"
    GROCERIES_FILE = "groceries"

Auto-increment IDs (AdminID / CustomerID / ItemID) are handled with a
"counters" collection + atomic $inc, which avoids the read-then-write race
condition the old max(existing_ids)+1 approach had on Sheets.
"""

import os
import re
import json
from pymongo import MongoClient, ReturnDocument, ASCENDING

ADMINS_FILE = "admins"
CUSTOMERS_FILE = "customers"
GROCERIES_FILE = "groceries"

ADMIN_HEADERS = ["AdminID", "Name", "Email", "Phone", "PasswordHash", "CreatedAt"]
CUSTOMER_HEADERS = ["CustomerID", "Name", "Email", "Phone", "PasswordHash", "TransactionHistory", "CreatedAt"]
GROCERY_HEADERS = ["ItemID", "Name", "Category", "Unit", "PricePerUnit", "QuantityInStock", "ImageURL"]

_client = None
_db = None


def _get_db():
    global _client, _db
    if _db is not None:
        return _db
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise ValueError("MONGODB_URI environment variable not set")
    _client = MongoClient(uri)
    # Uses the database named in the URI path (e.g. .../freshcart?...).
    # Falls back to "freshcart" if the URI has no db name in the path.
    _db = _client.get_default_database(default="freshcart")
    return _db


def _get_collection(name):
    return _get_db()[name]


def _counters():
    return _get_db()["counters"]


def _next_id(collection_name, id_column):
    counter = _counters().find_one_and_update(
        {"_id": f"{collection_name}.{id_column}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return counter["seq"]


def _id_candidates(id_value):
    """Match both the string form and int form of an ID, since callers
    sometimes pass a URL/session string ('7') and sometimes an int."""
    candidates = [id_value]
    try:
        candidates.append(int(id_value))
    except (TypeError, ValueError):
        pass
    return candidates


def get_all_rows(collection_name):
    col = _get_collection(collection_name)
    return list(col.find({}, {"_id": 0}))


def get_row_by_id(collection_name, id_column, id_value):
    col = _get_collection(collection_name)
    return col.find_one({id_column: {"$in": _id_candidates(id_value)}}, {"_id": 0})


def get_row_by_email(collection_name, email):
    if not email:
        return None
    col = _get_collection(collection_name)
    target = re.escape(email.strip().lower())
    return col.find_one({"Email": {"$regex": f"^{target}$", "$options": "i"}}, {"_id": 0})


def create_record(collection_name, id_column, data):
    col = _get_collection(collection_name)
    new_id = _next_id(collection_name, id_column)
    record = dict(data)
    record[id_column] = new_id
    col.insert_one(record)
    return new_id


def update_row(collection_name, id_column, id_value, updates):
    col = _get_collection(collection_name)
    result = col.update_one(
        {id_column: {"$in": _id_candidates(id_value)}},
        {"$set": dict(updates)},
    )
    return result.matched_count > 0


def init_db():
    """Ping Atlas and make sure useful indexes exist. Call once at app
    startup (replaces the old init_excel_files())."""
    try:
        db = _get_db()
        db.client.admin.command("ping")
        db[ADMINS_FILE].create_index([("Email", ASCENDING)])
        db[ADMINS_FILE].create_index([("AdminID", ASCENDING)], unique=True)
        db[CUSTOMERS_FILE].create_index([("Email", ASCENDING)])
        db[CUSTOMERS_FILE].create_index([("CustomerID", ASCENDING)], unique=True)
        db[GROCERIES_FILE].create_index([("ItemID", ASCENDING)], unique=True)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize MongoDB: {e}")


def parse_transaction_history(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def serialize_transaction_history(history_list):
    return json.dumps(history_list)
