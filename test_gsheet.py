
from gsheet_handler import gsheet_logger
import datetime

print("🔗 連接 Google Sheet: Stock_Bot_Log ...")
if gsheet_logger.connect():
    print("✅ 認證成功！")
    
    test_data = {
        "symbol": "TEST.TW",
        "action": "CONNECTION_TEST",
        "price": 100,
        "qty": 1,
        "amount": 100,
        "fee": 0,
        "tax": 0,
        "balance": 0,
        "msg": "Test from Antigravity"
    }
    
    print("📝 嘗試寫入測試資料...")
    if gsheet_logger.log_trade("Stock_Bot_Log", test_data):
        print("🎉 寫入成功！請檢查您的 Google Sheet。")
    else:
        print("❌ 寫入失敗。請確認試算表名稱正確且已分享給機器人。")
else:
    print("❌ 這證失敗。請檢查 google_key.json。")
