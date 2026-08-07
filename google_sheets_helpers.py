import os, json, base64
from threading import Lock
import gspread
from google.auth.service_account import Credentials

ADMINS_SHEET_ID = os.environ.get("ADMINS_SHEET_ID", "1kfZuYSZJ4LyVYcbU5WQk5zJslhYzETtj23qbDLNDuE8")
CUSTOMERS_SHEET_ID = os.environ.get("CUSTOMERS_SHEET_ID", "14gT1SFByZeltkRPqgkFtoYwA0yYtZx_92yFm3I0a61E")
GROCERIES_SHEET_ID = os.environ.get("GROCERIES_SHEET_ID", "1JR1W2OiuuKJmbp4uQAdbN4xr9hNHymn2kE3HXXqQm0s")

ADMIN_HEADERS = ["AdminID", "Name", "Email", "Phone", "PasswordHash", "CreatedAt"]
CUSTOMER_HEADERS = ["CustomerID", "Name", "Email", "Phone", "PasswordHash", "TransactionHistory", "CreatedAt"]
GROCERY_HEADERS = ["ItemID", "Name", "Category", "Unit", "PricePerUnit", "QuantityInStock", "ImageURL"]

_lock = Lock()
_client = None

def _get_gspread_client():
    global _client
    if _client is not None:
        return _client
    creds_b64 = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_b64:
        raise ValueError("GOOGLE_SHEETS_CREDENTIALS environment variable not set")
    try:
        creds_json = base64.b64decode(creds_b64).decode("utf-8")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        _client = gspread.authorize(creds)
        return _client
    except Exception as e:
        raise ValueError(f"Failed to load credentials: {e}")

def _get_worksheet(sheet_id):
    client = _get_gspread_client()
    sheet = client.open_by_key(sheet_id)
    return sheet.sheet1

def _read_rows(sheet_id):
    with _lock:
        ws = _get_worksheet(sheet_id)
        rows = ws.get_all_values()
        if not rows:
            return []
        headers = rows[0]
        result = []
        for raw_row in rows[1:]:
            if not raw_row or raw_row[0] == "":
                continue
            row_dict = dict(zip(headers, raw_row))
            result.append(row_dict)
        return result

def get_all_rows(sheet_id):
    return _read_rows(sheet_id)

def get_row_by_id(sheet_id, id_column, id_value):
    for row in _read_rows(sheet_id):
        if row.get(id_column) and str(row[id_column]) == str(id_value):
            return row
    return None

def get_row_by_email(sheet_id, email):
    if not email:
        return None
    target = email.strip().lower()
    for row in _read_rows(sheet_id):
        stored = row.get("Email")
        if stored and str(stored).strip().lower() == target:
            return row
    return None

def create_record(sheet_id, id_column, data):
    with _lock:
        ws = _get_worksheet(sheet_id)
        rows = ws.get_all_values()
        headers = rows[0] if rows else []
        if id_column not in headers:
            raise ValueError(f"Column {id_column} not in sheet headers")
        id_idx = headers.index(id_column)
        existing_ids = []
        for row in rows[1:]:
            if row and row[id_idx]:
                try:
                    existing_ids.append(int(row[id_idx]))
                except ValueError:
                    pass
        new_id = (max(existing_ids) + 1) if existing_ids else 1
        record = dict(data)
        record[id_column] = new_id
        new_row = [record.get(h, "") for h in headers]
        ws.append_row(new_row)
        return new_id

def update_row(sheet_id, id_column, id_value, updates):
    with _lock:
        ws = _get_worksheet(sheet_id)
        rows = ws.get_all_values()
        if not rows:
            return False
        headers = rows[0]
        if id_column not in headers:
            return False
        id_idx = headers.index(id_column)
        found_row_num = None
        for row_num, row in enumerate(rows[1:], start=2):
            if row and row[id_idx] and str(row[id_idx]) == str(id_value):
                found_row_num = row_num
                break
        if found_row_num is None:
            return False
        for key, value in updates.items():
            if key in headers:
                col_idx = headers.index(key) + 1
                ws.update_cell(found_row_num, col_idx, value)
        return True

ADMINS_FILE = ADMINS_SHEET_ID
CUSTOMERS_FILE = CUSTOMERS_SHEET_ID
GROCERIES_FILE = GROCERIES_SHEET_ID

def init_excel_files():
    try:
        _get_gspread_client()
        _get_worksheet(ADMINS_SHEET_ID)
        _get_worksheet(CUSTOMERS_SHEET_ID)
        _get_worksheet(GROCERIES_SHEET_ID)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize: {e}")

def parse_transaction_history(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []

def serialize_transaction_history(history_list):
    return json.dumps(history_list)
