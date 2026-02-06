import json
import os

key_path = "google_key.json"

if not os.path.exists(key_path):
    print(f"❌ 找不到檔案: {key_path}")
    print("請確認您已將下載的 JSON 檔案改名為 google_key.json 並放在專案根目錄。")
else:
    try:
        with open(key_path, "r", encoding='utf-8') as f:
            data = json.load(f)
            email = data.get("client_email", "找不到 client_email 欄位")
            print("\n🤖 機器人 Email (請複製這個 Email 去分享您的 Google Sheet):")
            print("="*60)
            print(f"{email}")
            print("="*60)
    except Exception as e:
        print(f"❌ 讀取錯誤: {e}")
