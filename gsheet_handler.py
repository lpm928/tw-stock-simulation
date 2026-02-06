import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import os
import streamlit as st

# Scope for GSheets/Drive
SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

KEY_FILE = 'google_key.json'

class GSheetHandler:
    def __init__(self, key_file=KEY_FILE):
        self.client = None
        self.key_file = key_file
        self.connected = False
        
    def connect(self):
        """Authenticates with Google Sheets API"""
        try:
            # Check Streamlit Secrets first (safe check)
            try:
                if "gcp_service_account" in st.secrets:
                    self.client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
                    self.connected = True
                    return True
            except FileNotFoundError:
                pass # Local run without secrets.toml
            except Exception:
                pass 

            # Fallback to Local Key
            if os.path.exists(self.key_file):
                creds = ServiceAccountCredentials.from_json_keyfile_name(self.key_file, SCOPE)
                self.client = gspread.authorize(creds)
                self.connected = True
                return True
            else:
                print("No credentials found (google_key.json or st.secrets)")
                return False

        except Exception as e:
            print(f"GSheet Auth Error: {e}")
            return False

    def log_trade(self, sheet_name, trade_data):
        """
        Logs a trade dictionary to the first worksheet.
        trace_data: dict with keys like date, symbol, action, price, qty, etc.
        """
        if not self.client:
            if not self.connect(): return False
            
        try:
            sh = self.client.open(sheet_name)
            ws = sh.sheet1 # Use first sheet
            
            # Ensure Headers if empty
            if not ws.get_all_values():
                headers = ["Date", "Symbol", "Action", "Price", "Qty", "Amount", "Fee", "Tax", "Balance", "Msg"]
                ws.append_row(headers)
                
            # Prepare row
            row = [
                str(datetime.datetime.now()),
                trade_data.get('symbol', ''),
                trade_data.get('action', ''),
                trade_data.get('price', 0),
                trade_data.get('qty', 0),
                trade_data.get('amount', 0),
                trade_data.get('fee', 0),
                trade_data.get('tax', 0),
                trade_data.get('balance', 0),
                trade_data.get('msg', '')
            ]
            
            ws.append_row(row)
            return True
        except Exception as e:
            print(f"GSheet Log Error: {e}")
            return False


    def log_user(self, sheet_name, username):
        """
        Logs a new user registration.
        """
        if not self.client:
            if not self.connect(): return False
            
        try:
            sh = self.client.open(sheet_name)
            
            # Try to get or create "Users" worksheet
            try:
                ws = sh.worksheet("Users")
            except:
                ws = sh.add_worksheet(title="Users", rows=100, cols=5)
                
            # Ensure Headers
            if not ws.get_all_values():
                ws.append_row(["Register Time", "Username", "Status"])
                
            ws.append_row([str(datetime.datetime.now()), username, "Active"])
            return True
        except Exception as e:
            print(f"GSheet User Log Error: {e}")
            return False

    # --- Cloud DB Methods ---
    def fetch_all_users(self, sheet_name):
        """Returns dict {username: password_hash}"""
        if not self.client:
            if not self.connect(): return {}
            
        try:
            sh = self.client.open(sheet_name)
            try:
                ws = sh.worksheet("Users")
            except:
                return {} # No users sheet yet
                
            records = ws.get_all_records() # Expects headers: Register Time, Username, PasswordHash...
            # Compatibility with existing log_user structure which didn't have PasswordHash
            # Existing header: ["Register Time", "Username", "Status"]
            # We need to upgrade if necessary or just robustly check
            
            user_db = {}
            for r in records:
                u = r.get("Username")
                p = r.get("PasswordHash")
                if u and p:
                    user_db[u] = str(p) # Ensure string
            return user_db
        except Exception as e:
            print(f"Fetch Users Error: {e}")
            return {}

    def register_user_db(self, sheet_name, username, password_hash):
        if not self.client:
            if not self.connect(): return False
            
        try:
            sh = self.client.open(sheet_name)
            try:
                ws = sh.worksheet("Users")
            except:
                ws = sh.add_worksheet(title="Users", rows=100, cols=5)
                
            # Check Headers
            headers = ws.row_values(1)
            required = ["Register Time", "Username", "PasswordHash", "Status"]
            if not headers or headers[:2] != ["Register Time", "Username"]: 
                # Init headers
                ws.clear()
                ws.append_row(required)
            elif "PasswordHash" not in headers:
                # Upgrade headers - primitive
                # For now assuming we control it.
                pass

            ws.append_row([str(datetime.datetime.now()), username, password_hash, "Active"])
            return True
        except Exception as e:
            print(f"Register DB Error: {e}")
            return False

    def save_user_data(self, sheet_name, username, data_dict):
        """
        Saves user state (JSON) to UserData sheet. Upstream (Upsert).
        """
        import json
        if not self.client:
            if not self.connect(): return False
            
        try:
            sh = self.client.open(sheet_name)
            try:
                ws = sh.worksheet("UserData")
            except:
                ws = sh.add_worksheet(title="UserData", rows=100, cols=5)
                ws.append_row(["Username", "UpdatedAt", "DataJSON"])
            
            json_str = json.dumps(data_dict, ensure_ascii=False)
            now = str(datetime.datetime.now())
            
            # Upsert Logic
            # 1. Find row
            cell = ws.find(username, in_column=1)
            if cell:
                # Update
                ws.update_cell(cell.row, 2, now)
                ws.update_cell(cell.row, 3, json_str)
            else:
                # Insert
                ws.append_row([username, now, json_str])
            return True
        except Exception as e:
            print(f"Save UserData Error: {e}")
            return False

    def fetch_user_data(self, sheet_name, username):
        import json
        if not self.client:
            if not self.connect(): return None
            
        try:
            sh = self.client.open(sheet_name)
            try:
                ws = sh.worksheet("UserData")
            except:
                return None
            
            cell = ws.find(username, in_column=1)
            if cell:
                json_str = ws.cell(cell.row, 3).value
                return json.loads(json_str)
            return None
        except Exception as e:
            print(f"Fetch UserData Error: {e}")
            return None

# Global Instance
gsheet_logger = GSheetHandler()
