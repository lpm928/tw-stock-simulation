
import json
import os
from gsheet_handler import gsheet_logger

USER_DB_FILE = "users.json"

def migrate():
    print("🚀 開始雲端搬家作業 (Cloud Migration)...")
    print("目標試算表: Stock_Bot_Log")
    
    if not gsheet_logger.connect():
        print("❌ 無法連接 Google Sheets，請檢查 key 或網路。")
        return

    # 1. Migrate Users (Auth)
    print("\n[1/2] 正在同步使用者帳號...")
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, "r", encoding='utf-8') as f:
                users = json.load(f)
            
            count = 0
            for u, p_hash in users.items():
                print(f"  - 上傳使用者: {u} ...", end="")
                if gsheet_logger.register_user_db("Stock_Bot_Log", u, p_hash):
                    print(" OK")
                    count += 1
                else:
                    print(" Fail")
            print(f"✅ 完成，共 {count} 位使用者。")
        except Exception as e:
            print(f"❌ 讀取 users.json 失敗: {e}")
    else:
        print("⚠️ 找不到 users.json，跳過。")

    # 2. Migrate User Data
    print("\n[2/2] 正在同步使用者資料 (庫存/紀錄)...")
    if os.path.exists(USER_DB_FILE): # Iterate known users
        for u in users.keys():
            data_file = f"user_{u}.json"
            if os.path.exists(data_file):
                print(f"  - 上傳 {u} 的資料 ({data_file}) ...", end="")
                try:
                    with open(data_file, "r", encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if gsheet_logger.save_user_data("Stock_Bot_Log", u, data):
                        print(" OK")
                    else:
                        print(" Fail")
                except Exception as e:
                    print(f" Error: {e}")
            else:
                print(f"  - {u} 沒有資料檔，跳過。")
                
    print("\n🎉 搬家完成！")
    print("現在您可以直接部署到雲端，資料都不會消失了！")

if __name__ == "__main__":
    migrate()
