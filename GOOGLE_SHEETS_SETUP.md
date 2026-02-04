# 🔐 Google Sheets 整合與資安設定指南

若您計畫讓此平台連接 Google Sheets 進行雲端資料儲存 (例如：即時備份交易紀錄、讀取外部策略訊號)，請務必遵守以下資安規範。

## 1. 申請 Google Cloud Service Account (服務帳號)

Google Sheets API 需要透過 Google Cloud Platform (GCP) 的服務帳號進行驗證。

1.  前往 [Google Cloud Console](https://console.cloud.google.com/)。
2.  建立一個新專案 (Project)，例如取名為 `Stock-Bot`。
3.  在左側選單進入 **「APIs & Services」 > 「Library」**。
4.  搜尋並啟用以下兩個 API：
    *   **Google Sheets API**
    *   **Google Drive API** (若需要讀寫權限通常建議開啟)
5.  進入 **「IAM & Admin」 > 「Service Accounts」**。
6.  點擊 **「Create Service Account」**，取個名字 (如 `stock-bot-worker`)。
7.  建立後，點擊該帳號，進入 **「Keys」** 分頁。
8.  點擊 **「Add Key」 > 「Create new key」**，選擇 **JSON** 格式。
9.  **下載 JSON 金鑰檔案** (這就是您的鑰匙，請妥善保管！)。

## 2. ⚠️ 資安關鍵設定 (DO NOT COMMIT)

**絕對不要** 將此 JSON 檔案上傳到 GitHub！一旦上傳，駭客可在幾秒內掃描到並盜用您的雲端資源。

### 本地開發 (Local Development)
1.  將下載的 JSON 檔案重新命名為 `google_key.json` (或其他好記的名字)。
2.  將此檔案放在專案根目錄。
3.  **確認 `.gitignore` 檔案中已包含 `*.json` 或 `google_key.json`** (本專案已為您設定)。

### 雲端部署 (Streamlit Cloud / Zeabur / Heroku)
若您部屬到雲端，**不要** 上傳 JSON 檔案。請使用環境變數或 Secrets 管理功能。

**以 Streamlit Cloud 為例**：
1.  在部署後台找到 **「Advanced Settings」 > 「Secrets」**。
2.  將 JSON 的內容複製，貼上並轉為 TOML 格式：
    ```toml
    [gcp_service_account]
    type = "service_account"
    project_id = "your-project-id"
    private_key_id = "..."
    private_key = "-----BEGIN PRIVATE KEY-----..."
    client_email = "..."
    # ... 其他欄位
    ```
3.  在程式碼中透過 `st.secrets["gcp_service_account"]` 讀取。

## 3. 設定 Google Sheets 權限

1.  打開您想讓權限連接的 Google Sheet 試算表。
2.  點擊右上角的 **「共用 (Share)」**。
3.  在邀請框中，輸入您的 **Service Account Email** (長得像 `stock-bot-worker@project-id.iam.gserviceaccount.com`)。
4.  賦予 **「編輯者 (Editor)」** 權限。

---

## 4. 程式碼整合範例 (Python)

```python
import gspread
import streamlit as st

def connect_gsheet():
    try:
        # 本地端讀取檔案，雲端讀取 Secrets
        if "gcp_service_account" in st.secrets:
            gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        else:
            gc = gspread.service_account(filename="google_key.json")
            
        sh = gc.open("您的試算表名稱")
        return sh
    except Exception as e:
        st.error(f"Google Sheets 連線失敗: {e}")
        return None
```
