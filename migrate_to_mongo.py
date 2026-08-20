"""
One-time migration: Google Sheets -> MongoDB Atlas.

Run this ONCE, locally or as a Render Shell command, after:
  - MONGODB_URI is set in the environment
  - GOOGLE_SHEETS_CREDENTIALS / ADMINS_SHEET_ID / CUSTOMERS_SHEET_ID /
    GROCERIES_SHEET_ID are still set (this script needs both sides)

Usage:
    python migrate_to_mongo.py

It copies every row from the 3 sheets into the 3 Mongo collections,
converting numeric fields to real numbers, and sets the Mongo ID counters
to continue from the highest existing ID (so new records don't collide).

Safe to re-run: it clears the target collections first (only the ones
this script writes to) rather than appending duplicates.
"""

import os
from google_sheets_helpers import (
    ADMINS_SHEET_ID, CUSTOMERS_SHEET_ID, GROCERIES_SHEET_ID,
    get_all_rows,
)
from mongo_helpers import (
    _get_db, ADMINS_FILE, CUSTOMERS_FILE, GROCERIES_FILE, init_db,
)

NUMERIC_FIELDS = {
    "groceries": {"PricePerUnit": float, "QuantityInStock": int, "ItemID": int},
    "customers": {"CustomerID": int},
    "admins": {"AdminID": int},
}


def _coerce(collection_name, row):
    out = dict(row)
    for field, caster in NUMERIC_FIELDS.get(collection_name, {}).items():
        if field in out and out[field] != "":
            try:
                out[field] = caster(out[field])
            except (ValueError, TypeError):
                pass
    return out


def migrate_one(sheet_id, collection_name, id_column):
    rows = get_all_rows(sheet_id)
    db = _get_db()
    col = db[collection_name]
    col.delete_many({})
    if rows:
        docs = [_coerce(collection_name, r) for r in rows]
        col.insert_many(docs)
    max_id = 0
    for r in rows:
        try:
            max_id = max(max_id, int(r.get(id_column, 0)))
        except (ValueError, TypeError):
            pass
    db["counters"].update_one(
        {"_id": f"{collection_name}.{id_column}"},
        {"$set": {"seq": max_id}},
        upsert=True,
    )
    print(f"  {collection_name}: migrated {len(rows)} rows, counter set to {max_id}")


def main():
    if not os.environ.get("MONGODB_URI"):
        raise SystemExit("MONGODB_URI is not set — set it before running this script.")
    print("Connecting to MongoDB Atlas...")
    init_db()
    print("Migrating groceries...")
    migrate_one(GROCERIES_SHEET_ID, GROCERIES_FILE, "ItemID")
    print("Migrating customers...")
    migrate_one(CUSTOMERS_SHEET_ID, CUSTOMERS_FILE, "CustomerID")
    print("Migrating admins...")
    migrate_one(ADMINS_SHEET_ID, ADMINS_FILE, "AdminID")
    print("Done. Verify the data in Atlas, then swap the imports over to mongo_helpers.")


if __name__ == "__main__":
    main()
