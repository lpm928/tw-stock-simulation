
import google.generativeai as genai
import streamlit as st
import pandas as pd
import datetime

import time

def get_gemini_response(api_key, model_name, prompt_text):
    """
    Calls Gemini API with the provided key and prompt.
    Returns a stream or text.
    Attributes:
        Retry logic for 429 (Resource Exhausted) errors.
    """
    if not api_key:
        return "⚠️ 請輸入 API 金鑰 (Please enter API Key)"
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    max_retries = 3
    base_delay = 5 # Start with 5 seconds
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt_text, stream=True)
            return response
            
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                if attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt) # 5, 10, 20
                    st.toast(f"⏳ AI 額度流量管制中，將於 {wait_time} 秒後重試... ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"❌ AI 分析服務暫時無法使用 (額度已滿)。請稍後再試，或檢查您的 Google Plan。\n\n詳細錯誤: {err_str}"
            else:
                return f"❌ AI 分析發生錯誤: {err_str}"

def get_available_models(api_key):
    """
    Fetches available models for the given API key.
    Returns a list of model names (e.g. ['gemini-pro', ...])
    """
    if not api_key:
        return ["gemini-1.5-flash"] # Default fallback

    try:
        genai.configure(api_key=api_key)
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name.replace("models/", "")
                if "gemini" in name: # Filter for Gemini models
                    models.append(name)
        
        models.sort(reverse=True) 
        return models if models else ["gemini-1.5-flash"]
        
    except Exception as e:
        return [f"Error: {e}", "gemini-1.5-flash"]


def construct_stock_prompt(stock_id, stock_name, price_data, fund_data, inst_data, chips_data, inc_df, div_df, news_list):
    """
    Builds a rich prompt for the AI including Financials, Dividends and News.
    """
    
    # 1. Summarize Price
    latest_price = price_data.iloc[-1]['Close'] if not price_data.empty else "N/A"
    
    # 2. Summarize Chips
    inst_summary = "無資料"
    if not inst_data.empty:
        last5 = inst_data.tail(5).sum()
        inst_summary = f"外資近5日: {last5.get('Foreign_Net', 0):.0f}, 投信: {last5.get('Trust_Net', 0):.0f}"
        
    chips_trend = "無資料"
    if not chips_data.empty:
        # Check if we have enough rows
        last_chip = chips_data.iloc[-1]['HoldingProportion']
        prev_chip = chips_data.iloc[0]['HoldingProportion']
        chips_trend = f"大戶持股比例: {last_chip}% (從 {prev_chip}% 變化)"

    # 3. Summarize Financials (Revenue Growth, etc)
    # Take latest quarter vs previous if available
    fin_summary = "無詳細財報"
    if not inc_df.empty:
        try:
            # Example: Total Revenue
            rev_row = inc_df.loc['Total Revenue'] if 'Total Revenue' in inc_df.index else pd.Series()
            if not rev_row.empty:
                latest_rev = rev_row.iloc[0] # Most recent
                fin_summary = f"最新季營收: {latest_rev/100000000:.2f}億 (台幣)"
        except:
            pass
            
    # 4. Summarize Dividends
    div_summary = "無配息資料"
    if not div_df.empty:
        last_div = div_df.iloc[0]['Dividend']
        last_date = div_df.index[0].strftime('%Y-%m-%d')
        div_summary = f"最近一次配息: {last_div} 元 ({last_date})"

    # 5. Summarize News (Headlines)
    news_summary = ""
    if news_list:
        headlines = [f"- {n.get('title', 'No Title')} ({n.get('publisher', '')})" for n in news_list[:3]]
        news_summary = "\n".join(headlines)

    current_date = datetime.date.today().strftime("%Y-%m-%d")

    prompt = f"""
    角色：你是一位華爾街頂級的專業股票分析師 (Senior Equity Research Analyst)，擅長結合技術面、基本面、籌碼面與市場消息進行深度分析。
    
    【分析時間】 {current_date} (請以此為當下時間基準)
    
    任務：請針對以下台股標的進行詳細的投資分析報告。
    
    【1. 標的資訊】
    *   股票代號：{stock_name} ({stock_id})
    *   目前股價：{latest_price}
    
    【2. 基本面數據 (Fundamentals)】
    *   EPS: {fund_data.get('EPS (Trailing)', 'N/A')}
    *   ROE: {fund_data.get('ROE', 'N/A')}
    *   P/E Ratio: {fund_data.get('P/E Ratio', 'N/A')}
    *   殖利率: {fund_data.get('Dividend Yield', 'N/A')}
    *   財報概況: {fin_summary}
    *   配息概況: {div_summary}
    
    【3. 籌碼面數據 (Chips Analysis)】
    *   法人動向: {inst_summary}
    *   大戶籌碼: {chips_trend}
    
    【4. 近期市場新聞 (News Context)】
    {news_summary}
    
    【分析要求】
    1.  **綜合評語**：一句話總結目前的趨勢 (多頭/空頭/盤整)。
    2.  **基本面解讀**：結合營收、EPS 與配息能力進行評估。
    3.  **消息面影響**：根據提供的新聞標題，判斷近期是否有重大題材或利空。
    4.  **操作建議**：根據當前數據，給出具體建議 (例如：拉回買進、突破追價、觀望)。
    
    請用專業、客觀且條理分明的語氣回答 (繁體中文)。
    """
    return prompt
