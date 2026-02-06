import json

try:
    with open("google_key.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print("\n🔻 請複製下方內容到 Streamlit Secrets 🔻")
    print("==========================================")
    print("[gcp_service_account]")
    for k, v in data.items():
        # Handle Private Key (Multiline)
        if k == "private_key":
            # TOML multiline string
            print(f'{k} = """{v}"""')
        else:
            print(f'{k} = "{v}"')
    print("==========================================")
except FileNotFoundError:
    print("❌ 找不到 google_key.json，請確認檔案在專案根目錄。")
except Exception as e:
    print(f"❌ 錯誤: {e}")
