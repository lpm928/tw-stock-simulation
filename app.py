import streamlit as st
import datetime
import time
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
from utils import fetch_twse_institutional_data, get_stock_data, get_latest_price, get_realtime_quote, get_top_movers_batch, get_sector_performance
from broker import PaperBroker
from strategy import check_strategy, calculate_indicators, get_signal, get_strategy_status
from backtest import BacktestEngine
from data_manager import save_data, load_data
from stock_map import get_stock_name, STOCK_NAMES
from ui_resources import ST_STYLE, MANUAL_TEXT
from utils import fetch_twse_institutional_data, get_stock_data, get_latest_price, get_realtime_quote, get_top_movers_batch, get_sector_performance, get_fundamental_data, fetch_shareholding_data, get_financial_statement, get_dividend_history, get_recent_news
from broker import PaperBroker
from strategy import check_strategy, calculate_indicators, get_signal, get_strategy_status
from backtest import BacktestEngine
from data_manager import save_data, load_data
from stock_map import get_stock_name, STOCK_NAMES
from ui_resources import ST_STYLE, MANUAL_TEXT
from auth import render_login_ui
from ai_advisor import get_gemini_response, construct_stock_prompt, get_available_models
from prediction_engine import prepare_data, train_xgboost

# Set page config
st.set_page_config(page_title="台股智投旗艦版", layout="wide", page_icon="📈")

# --- UI Theme Injection ---
st.markdown(ST_STYLE, unsafe_allow_html=True)

def persist():
    save_data(
        st.session_state.broker, 
        st.session_state.watchlists, 
        st.session_state.trade_log,
        st.session_state.bot_config,
        username=st.session_state.get('username', 'default')
    )

def main_app():
    # Auto-refresh moved to page specific logic

    
    # --- Global Sidebar ---
    st.sidebar.title(f"👤 {st.session_state.get('username', 'User')}")
    if st.sidebar.button("登出"):
        st.session_state['logged_in'] = False
        st.rerun()
        
    st.sidebar.subheader("🗂️ 自選股")
    if st.session_state.active_list not in st.session_state.watchlists:
        st.session_state.active_list = list(st.session_state.watchlists.keys())[0] if st.session_state.watchlists else "Default"
        if "Default" not in st.session_state.watchlists: st.session_state.watchlists["Default"] = ["2330.TW"]

    act_list = st.sidebar.selectbox("切換清單", list(st.session_state.watchlists.keys()), index=list(st.session_state.watchlists.keys()).index(st.session_state.active_list))
    st.session_state.active_list = act_list
    codes = st.session_state.watchlists[act_list]

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🏛️ 大盤指數")
    try:
        # Use new Realtime Quote function
        q_twii = get_realtime_quote("^TWII")
        
        if q_twii['price'] > 0:
            color_class = "metric-up" if q_twii['change'] > 0 else "metric-down"
            st.sidebar.markdown(f"""
            <div data-testid="stMetric" class="stMetric">
                <label data-testid="stMetricLabel" class="css-1">加權指數 ({q_twii['time']})</label>
                <div data-testid="stMetricValue" class="css-1 {color_class}">
                    {q_twii['price']:,.0f} <span style="font-size: 1rem;">{q_twii['change']:+.0f} ({q_twii['pct']:+.2f}%)</span>
                </div>
                <div style="font-size: 0.8rem; color: #888; margin-top: 5px;">
                    昨收: {q_twii['prev_close']:,.0f}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        else:
            st.sidebar.metric("加權指數", "連線中...")
    except:
        st.sidebar.metric("加權指數", "N/A")

    # --- Navigation ---
    page = st.sidebar.radio("功能導覽", ["🖥️ 模擬操盤室", "📊 盤後分析", "🔬 個股研究室", "🧠 AI 預測實驗室", "🤖 智能機器人", "🔬 回測實驗室", "📚 使用指南"], index=0)

    # ==========================================
    # PAGE: STOCK RESEARCH (AI + Data)
    # ==========================================
    if page == "🤖 智能機器人":
        st.title("🤖 智能自動交易機器人")
        st.info("⚠️ 請保持此頁面開啟，機器人才能持續監控盤勢。")
        
        # Auto-refresh for Bot (60s to save quota)
        count = st_autorefresh(interval=60000, key="bot_refresh")
    elif page == "🔬 個股研究室":
        st.title("🔬 個股全方位研究室")
        st.caption("整合基本面、籌碼面與 AI 智能分析 (Integrating Fundamentals, Chips & AI)")
        
        # --- Input Section ---
        col_input, col_ai_key = st.columns([1, 2])
        with col_input:
            target = st.text_input("輸入股票代號 (e.g. 2330)", value="2330", key="stock_code_input")
            target_code = target.split(".")[0] + ".TW" if "." not in target else target
            stock_name = get_stock_name(target_code)
        
        with col_ai_key:
            api_key = st.text_input("🔑 Gemini API Key (AI 分析用)", type="password", key="ai_api_key_input", help="請輸入您的 Google Gemini API 金鑰以啟用 AI 分析功能")
            
            # Dynamic Model Selection
            if api_key:
                model_options = get_available_models(api_key)
            else:
                model_options = ["請先輸入 Key"]
                
            model_select = st.selectbox("選擇 AI 模型", model_options, key="ai_model_select")

        col_head, col_ref = st.columns([5, 1])
        with col_head: st.divider()
        with col_ref:
            if st.button("🔄 強制更新"):
                st.cache_data.clear()
                st.rerun()

        # --- Data Fetching ---
        if target:
            # 1. Price Data
            df_price = get_stock_data(target_code, period="6mo")
            quote = get_realtime_quote(target_code)
            
            # 2. Fundamental Data
            fund_data = get_fundamental_data(target_code)
            
            # 3. Institutional Data
            inst_data = fetch_twse_institutional_data(target.split(".")[0])
            
            # 4. Chips Data (Shareholding)
            chips_data = fetch_shareholding_data(target.split(".")[0])
            
            # 5. Financials & Dividends & News
            inc_df, bal_df = get_financial_statement(target_code)
            div_df = get_dividend_history(target_code)
            news_list = get_recent_news(target_code)

            # --- Layout: Header Metrics ---
            st.header(f"{stock_name} ({target_code})")
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("目前股價", f"{quote['price']}", f"{quote['pct']:.2f}%")
            m2.metric("EPS (Trailing)", fund_data.get('EPS (Trailing)', '-'))
            m3.metric("ROE", fund_data.get('ROE', '-'))
            m4.metric("殖利率", fund_data.get('Dividend Yield', '-'))
            m5.metric("本益比 P/E", fund_data.get('P/E Ratio', '-'))

            # --- Layout: Charts (Tabs) ---
            tab_tech, tab_chip, tab_fund, tab_news, tab_ai = st.tabs(["📉 技術走勢", "💰 籌碼分析", "📊 財報與配息", "📰 新聞快訊", "🤖 AI 智能報告"])
            
            with tab_tech:
                if not df_price.empty:
                    fig = go.Figure(go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Price"))
                    fig.update_layout(height=450, title=f"{stock_name} 日K線圖", template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
            
            with tab_chip:
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader("三大法人買賣超 (30日)")
                    if not inst_data.empty:
                         fig_inst = go.Figure()
                         fig_inst.add_trace(go.Bar(x=inst_data.index, y=inst_data.get('Foreign_Net', []), name='外資'))
                         fig_inst.add_trace(go.Bar(x=inst_data.index, y=inst_data.get('Trust_Net', []), name='投信'))
                         fig_inst.update_layout(height=400, barmode='stack', template="plotly_dark", legend=dict(orientation="h"))
                         st.plotly_chart(fig_inst, use_container_width=True)
                    else:
                        st.info("無法人數據")
                
                with c2:
                    st.subheader("大戶持股比例 (千張大戶)")
                    if not chips_data.empty:
                        fig_chip = px.line(chips_data, x="date", y="HoldingProportion", markers=True, title="大戶持股比例趨勢")
                        fig_chip.update_layout(height=400, template="plotly_dark")
                        st.plotly_chart(fig_chip, use_container_width=True)
                    else:
                        st.warning("⚠️ 無集保戶股權分散數據")
                        
            with tab_fund:
                f1, f2 = st.columns(2)
                with f1:
                    st.subheader("📊 損益表概況 (Quarterly)")
                    if not inc_df.empty:
                        st.dataframe(inc_df.iloc[:, :4], height=300) # Show last 4 quarters
                    else:
                        st.info("無財報數據")
                        
                with f2:
                    st.subheader("💵 歷年配息紀錄")
                    if not div_df.empty:
                        st.bar_chart(div_df.head(10)) # Show last 10 records
                    else:
                        st.info("無配息數據")
            
            with tab_news:
                st.subheader("📰 近期市場新聞")
                if news_list:
                    for n in news_list[:5]:
                        with st.expander(f"{n.get('title', 'No Title')} - {n.get('publisher', 'Unknown')}"):
                            st.write(f"Link: {n.get('link', '#')}")
                            # st.write(f"Published: {datetime.datetime.fromtimestamp(n.get('providerPublishTime', 0))}")
                else:
                    st.info("目前無相關新聞")

            with tab_ai:
                st.subheader("🤖 AI 趨勢分析報告")
                
                # Report Persistence Key
                report_key = f"ai_report_{target_code}"
                
                # Check for existing report
                if report_key in st.session_state:
                    st.success("✅ 已載入先前的分析報告")
                    st.markdown(st.session_state[report_key])
                    if st.button("🔄 重新生成報告"):
                        del st.session_state[report_key]
                        st.rerun()
                else:
                    if st.button("🚀 生成分析報告", type="primary"):
                        if not api_key:
                            st.error("請先在上方輸入 Gemini API Key")
                        else:
                            prompt_text = construct_stock_prompt(target_code, stock_name, df_price, fund_data, inst_data, chips_data, inc_df, div_df, news_list)
                            
                            st.markdown("### 分析生成中...")
                            res_box = st.empty()
                            full_text = ""
                            
                            response_stream = get_gemini_response(api_key, model_select, prompt_text)
                            
                            if isinstance(response_stream, str):
                                st.error(response_stream)
                            else:
                                for chunk in response_stream:
                                    txt = chunk.text
                                    full_text += txt
                                    res_box.markdown(full_text)
                                
                                # Store for persistence
                                st.session_state[report_key] = full_text
                                st.success("分析完成！報告已儲存。")
                            

    if page == "📊 盤後分析":
        st.title("📊 盤後籌碼分析實驗室")
        col_head, col_btn = st.columns([4, 1])
        with col_head:
            st.caption("提供大盤綜覽、強弱勢股排行與法人籌碼動向分析 (Source: Market Data)")
        with col_btn:
            if st.button("🔄 手動更新資料"):
                st.cache_data.clear() # Clear cache to force new data
                st.rerun()
        
        tab1, tab2, tab3 = st.tabs(["🏛️ 大盤與類股", "📈 強弱勢排行", "💰 法人籌碼"])
        
        # --- TAB 1: Market & Sector ---
        with tab1:
            m1, m2 = st.columns([1, 1])
            with m1:
                st.subheader("加權指數走勢")
                q = get_realtime_quote("^TWII")
                
                # Check colors
                c_func = lambda x: ":red" if x > 0 else ":green" if x < 0 else ""
                val_color = "red" if q['change'] > 0 else "green" if q['change'] < 0 else "white"
                
                st.markdown(f"""
                ### {q['price']:,.0f} <span style='color:{val_color}'>{q['change']:+.0f} ({q['pct']:+.2f}%)</span>
                """, unsafe_allow_html=True)
                
                # TAIEX Chart
                df_twii = get_stock_data("^TWII", period="6mo")
                if not df_twii.empty:
                    fig = go.Figure(data=[go.Candlestick(
                        x=df_twii.index,
                        open=df_twii['Open'], high=df_twii['High'], low=df_twii['Low'], close=df_twii['Close'],
                        name="TAIEX"
                    )])
                    fig.update_layout(height=400, xaxis_rangeslider_visible=False, template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True)

            with m2:
                st.subheader("🔥 類股/族群表現 (Proxy)")
                sec_df = get_sector_performance()
                if not sec_df.empty:
                    # Bar Chart
                    fig_sec = px.bar(
                        sec_df, x="Change", y="Sector", orientation='h', 
                        color="Change", color_continuous_scale=["green", "red"],
                        range_color=[-3, 3],
                        text_auto='.2f'
                    )
                    fig_sec.update_layout(height=400, yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig_sec, use_container_width=True)
                else:
                    st.warning("無法取得類股資料")

        # --- TAB 2: Top Movers ---
        with tab2:
            st.subheader("🚀 全市場強弱勢排行 (Top 100 Sample)")
            if st.button("🔄 刷新排行數據"):
                with st.spinner("正在掃描全市場數據..."):
                    gainers, losers, active = get_top_movers_batch()
                    
                    c1, c2, c3 = st.columns(3)
                    
                    def show_table(df, title, color_col):
                        st.markdown(f"**{title}**")
                        if not df.empty:
                            # Add Name
                            df['Name'] = [get_stock_name(t) for t in df.index]
                            df = df[['Name', 'Price', 'ChangePct', 'Volume']]
                            st.dataframe(
                                df.style.format({
                                    'Price': '{:.2f}', 
                                    'ChangePct': '{:+.2f}%',
                                    'Volume': '{:,.0f}'
                                }).background_gradient(subset=['ChangePct'], cmap=color_col),
                                height=400
                            )
                    
                    with c1: show_table(gainers, "📈 漲幅排行", "Reds")
                    with c2: show_table(losers, "📉 跌幅排行", "Greens_r") # Reverse green for drops
                    with c3: show_table(active, "🔥 成交量排行", "Blues")
            else:
                st.info("點擊按鈕載入最新排行 (為節省流量，不自動載入)")

        # --- TAB 3: Institutional ---
        with tab3:
            st.subheader("💰 個股法人動向 (外資/投信/自營商)")
            target = st.text_input("輸入代碼查看籌碼 (e.g. 2330)", value="2330")
            if target:
                target_code = target.split(".")[0] + ".TW" if "." not in target else target
                
                c_chart, c_data = st.columns([2, 1])
                
                with c_chart:
                    inst_df = fetch_twse_institutional_data(target.split(".")[0])
                    if not inst_df.empty:
                        # Stacked Bar
                        fig_inst = go.Figure()
                        fig_inst.add_trace(go.Bar(x=inst_df.index, y=inst_df.get('Foreign_Net', []), name='外資'))
                        fig_inst.add_trace(go.Bar(x=inst_df.index, y=inst_df.get('Trust_Net', []), name='投信'))
                        fig_inst.add_trace(go.Bar(x=inst_df.index, y=inst_df.get('Dealer_Net', []), name='自營商'))
                        
                        fig_inst.update_layout(barmode='stack', title=f"{get_stock_name(target_code)} - 法人買賣超", height=400, template="plotly_dark")
                        st.plotly_chart(fig_inst, use_container_width=True)
                    else:
                        st.warning("查無法人資料 (可能為非上市櫃或資料來源連線失敗)")
                
                with c_data:
                    # Also Stock Price
                    price_df = get_stock_data(target_code, period="1mo")
                    if not price_df.empty:
                         fig_p = go.Figure(go.Candlestick(x=price_df.index, open=price_df['Open'], high=price_df['High'], low=price_df['Low'], close=price_df['Close']))
                         fig_p.update_layout(title="股價走勢", height=400, template="plotly_dark")
                         st.plotly_chart(fig_p, use_container_width=True)
    if page == "🖥️ 模擬操盤室":
        st.title("🖥️ 台股模擬操盤室")
        # Auto-refresh for Trading Room (30s)
        count = st_autorefresh(interval=30000, key="trading_refresh")
        
        # --- 1. KPI Cards (Top Row) ---
        acc = st.session_state.broker.get_account_summary(current_prices={c: get_latest_price(c) for c in st.session_state.broker.inventory})
        
        # Check colors for PnL
        u_pnl = acc['Unrealized_PnL']
        r_pnl = acc.get('Realized_PnL', 0)
        u_color = "metric-up" if u_pnl > 0 else "metric-down" if u_pnl < 0 else ""
        r_color = "metric-up" if r_pnl > 0 else "metric-down" if r_pnl < 0 else ""

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("💰 總資產權益", f"${acc['Total_Assets']:,.0f}")
        with k2:
            st.metric("💵 可用現金", f"${acc['Balance']:,.0f}")
        with k3:
             # Custom HTML for PnL with Color
             st.markdown(f"""
             <div data-testid="stMetric" class="stMetric">
                 <label data-testid="stMetricLabel" class="css-1">未實現損益</label>
                 <div data-testid="stMetricValue" class="css-1 {u_color}">
                     ${u_pnl:,.0f}
                 </div>
             </div>
             """, unsafe_allow_html=True)
        with k4:
             st.markdown(f"""
             <div data-testid="stMetric" class="stMetric">
                 <label data-testid="stMetricLabel" class="css-1">已實現損益</label>
                 <div data-testid="stMetricValue" class="css-1 {r_color}">
                     ${r_pnl:,.0f}
                 </div>
             </div>
             """, unsafe_allow_html=True)
        
        st.write("") # Spacer

        # --- 2. Main Workspace (Chart + Order) ---
        
        # Selector defaults
        if not codes: codes = ["2330.TW"]
        
        # Layout: Chart (0.7) | Order (0.3)
        c_chart, c_order = st.columns([0.7, 0.3])
        
        with c_chart:
            # Ticker Selector & Controls
            c_sel, c_tf, c_ind = st.columns([0.2, 0.4, 0.4])
            with c_sel:
                target = st.selectbox("📌 標的", codes, format_func=lambda x: f"{x} {get_stock_name(x)}")
            
            with c_tf:
                tf_map = {
                    "1分": ("1d", "1m"),
                    "5分": ("5d", "5m"),
                    "15分": ("5d", "15m"),
                    "30分": ("5d", "30m"),
                    "60分": ("1mo", "60m"),
                    "日K": ("6mo", "1d"),
                    "週K": ("1y", "1wk"),
                    "月K": ("2y", "1mo")
                }
                tf_label = st.select_slider("週期", options=list(tf_map.keys()), value="日K")
                period, interval = tf_map[tf_label]
                
            with c_ind:
                indicators = st.multiselect("指標", ["MA", "布林通道", "RSI", "KD", "MACD"], default=["MA", "布林通道"])

            # Chart Logic
            with st.container(): # Pseudo Card
                # Fetch Data
                df = get_stock_data(target, period=period, interval=interval)
                
                if not df.empty:
                    # --- Indicator Calculation (On Histogram/Table, not persisted to DB) ---
                    # MA
                    df['MA5'] = df['Close'].rolling(5).mean()
                    df['MA10'] = df['Close'].rolling(10).mean()
                    df['MA20'] = df['Close'].rolling(20).mean()
                    df['MA60'] = df['Close'].rolling(60).mean()
                    
                    # BBands
                    if "布林通道" in indicators:
                        std = df['Close'].rolling(20).std()
                        df['BB_Up'] = df['MA20'] + (std * 2)
                        df['BB_Lo'] = df['MA20'] - (std * 2)
                        
                    # RSI
                    if "RSI" in indicators:
                        delta = df['Close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                        rs = gain / loss
                        df['RSI'] = 100 - (100 / (1 + rs))
                        
                    # KD (Stochastic)
                    if "KD" in indicators:
                         low_min = df['Low'].rolling(9).min()
                         high_max = df['High'].rolling(9).max()
                         df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
                         df['K'] = df['RSV'].ewm(com=2).mean() # Approx SMA
                         df['D'] = df['K'].ewm(com=2).mean()
                         
                    # MACD
                    if "MACD" in indicators:
                         exp12 = df['Close'].ewm(span=12, adjust=False).mean()
                         exp26 = df['Close'].ewm(span=26, adjust=False).mean()
                         df['MACD'] = exp12 - exp26
                         df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
                         df['MACD_Hist'] = df['MACD'] - df['Signal_Line']

                    # --- Plotting ---
                    # Determine Rows based on oscillators
                    rows = 2
                    row_h = [0.7, 0.3]
                    
                    has_osc = False
                    osc_list = [i for i in ["RSI", "KD", "MACD"] if i in indicators]
                    if osc_list:
                         rows = 3
                         row_h = [0.6, 0.2, 0.2]
                         has_osc = True
                    
                    fig = make_subplots(
                        rows=rows, cols=1, shared_xaxes=True, 
                        row_heights=row_h, vertical_spacing=0.03,
                        subplot_titles=(f"{target} {tf_label}線圖", "成交量", osc_list[0] if has_osc else "")
                    )
                    
                    # 1. Candlestick (Row 1)
                    fig.add_trace(go.Candlestick(
                        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                        increasing_line_color='#FF4B4B', decreasing_line_color='#00C853', name="K線"
                    ), row=1, col=1)
                    
                    # Overlays
                    if "MA" in indicators:
                        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='orange', width=1), name='MA5'), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='skyblue', width=1), name='MA20'), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='purple', width=1), name='MA60'), row=1, col=1)

                    if "布林通道" in indicators:
                        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Up'], line=dict(color='rgba(200,200,200,0.5)', width=1, dash='dot'), name='BB Upper'), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lo'], line=dict(color='rgba(200,200,200,0.5)', width=1, dash='dot'), name='BB Lower', fill='tonexty', fillcolor='rgba(255,255,255,0.05)'), row=1, col=1)

                    # 2. Volume (Row 2)
                    colors = ['#FF4B4B' if c >= o else '#00C853' for c, o in zip(df['Close'], df['Open'])]
                    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="成交量"), row=2, col=1)

                    # 3. Oscillators (Row 3 - Only showing the first selected one to avoid crowding)
                    if has_osc:
                         t_osc = osc_list[0] # Priority: 1st selected
                         if t_osc == "RSI":
                              fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#E1E1E1'), name='RSI'), row=3, col=1)
                              fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
                              fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
                         elif t_osc == "KD":
                              fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='#FFA500'), name='K'), row=3, col=1)
                              fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='#00BFFF'), name='D'), row=3, col=1)
                         elif t_osc == "MACD":
                              fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=['#FF4B4B' if x>0 else '#00C853' for x in df['MACD_Hist']], name='MACD Hist'), row=3, col=1)
                              fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='#E1E1E1'), name='DIF'), row=3, col=1)
                              fig.add_trace(go.Scatter(x=df.index, y=df['Signal_Line'], line=dict(color='#FFA500'), name='MACD'), row=3, col=1)

                    # Layout Polish
                    # X-Axis Formatting for Intraday
                    x_format = "%Y-%m-%d"
                    if "分" in tf_label:
                        x_format = "%H:%M" # Only show time for intraday to save space? Or "m-d H:M"?
                        # If multi-day intraday (e.g. 5d 5m), we need Day+Time
                        if "1分" in tf_label: x_format = "%H:%M" # 1 day
                        else: x_format = "%m-%d %H:%M"

                    fig.update_layout(
                        height=600, 
                        margin=dict(t=30, b=10, r=10, l=10),
                        paper_bgcolor='#1E1E1E', # Match Card Box
                        plot_bgcolor='rgba(0,0,0,0)',
                        font=dict(color='#E0E0E0'),
                        xaxis_rangeslider_visible=False,
                        hovermode="x unified"
                    )
                    fig.update_xaxes(
                        showgrid=True, gridcolor='#333', 
                        tickformat=x_format,
                        rangeslider_visible=False 
                    )
                    fig.update_yaxes(showgrid=True, gridcolor='#333')
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("無法顯示線圖 (無資料)")

        with c_order:
             # Order Panel Card
             st.markdown(f"""
             <div style="background-color: #1E1E1E; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 1px solid #444;">
                 <h3 style="color: white; margin-top: 0;">⚡ 快速下單</h3>
                 <div style="font-size: 0.9rem; color: #AAA;">{target} {get_stock_name(target)}</div>
             </div>
             """, unsafe_allow_html=True)
             
             # Get Realtime Price
             curr_p = 0
             t_time = ""
             try:
                 # Try to reuse DF if latest
                 if not df.empty and df.index[-1].date() == datetime.date.today():
                     curr_p = float(df['Close'].iloc[-1])
                     t_time = df.index[-1].strftime("%H:%M")
                 else:
                     curr_p = get_latest_price(target)
                     t_time = "Realtime"
             except:
                 pass
            
             st.metric("參考價", f"{curr_p:.2f}", help=f"時間: {t_time}")
             
             qty = st.number_input("股數 (Shares)", min_value=1000, step=1000, value=1000)
             est_cost = qty * curr_p
             
             st.write(f"預估金額: **${est_cost:,.0f}**")
             
             col_buy, col_sell = st.columns(2)
             with col_buy:
                 if st.button("🔴 買進", use_container_width=True):
                     s, m = st.session_state.broker.buy(target, curr_p, qty)
                     if s: st.success("委託成功"); st.toast(f"已買入 {target} {qty}張"); persist(); time.sleep(1); st.rerun()
                     else: st.error(m)
                     
             with col_sell:
                 if st.button("🟢 賣出", use_container_width=True):
                     s, m = st.session_state.broker.sell(target, curr_p, qty)
                     if s: st.success("委託成功"); st.toast(f"已賣出 {target} {qty}張"); persist(); time.sleep(1); st.rerun()
                     else: st.error(m)
                     
             # Information
             st.caption("手續費 0.1425% (低消20), 證交稅 0.3% (賣出收)")
             
             inv_qty = st.session_state.broker.inventory.get(target, {}).get('qty', 0)
             st.info(f"目前持倉: {inv_qty} 股")

        # --- 3. Bottom Tabs (Portfolio & History) ---
        st.write("")
        tab1, tab2, tab3 = st.tabs(["📦 持股庫存", "📜 交易紀錄", "📊 回測/績效"])
        
        with tab1:
            inv_data = []
            for s, v in st.session_state.broker.inventory.items():
                if v['qty'] != 0:
                     cur = get_latest_price(s)
                     cost = v['cost']
                     mkt_val = cur * v['qty']
                     # PnL logic for table
                     unr = (cur - cost) * v['qty']
                     # Color logic? Streamlit table doesn't support row color easily without stylo, 
                     # but we can format the float.
                     inv_data.append({
                         "代碼": s, "名稱": get_stock_name(s), 
                         "庫存": v['qty'], "均價": f"{cost:.2f}", 
                         "現價": f"{cur:.2f}", "市值": mkt_val, 
                         "未實現損益": unr,
                         "報酬率(%)": ((cur-cost)/cost)*100 if cost!=0 else 0
                     })
            if inv_data:
                df_inv = pd.DataFrame(inv_data)
                st.dataframe(df_inv.style.format({
                    "市值": "{:,.0f}", 
                    "未實現損益": "{:,.0f}",
                    "報酬率(%)": "{:,.2f}%"
                }), use_container_width=True)
            else:
                st.info("目前無持倉")
                
        with tab2:
            hist = st.session_state.broker.transaction_history
            if hist:
                st.dataframe(pd.DataFrame(hist[::-1]), use_container_width=True)
            else:
                st.caption("尚無交易紀錄")
                
        with tab3:
            st.write("### 歷史績效統計")
            # Simple aggregation
            if st.session_state.broker.transaction_history:
                df_h = pd.DataFrame(st.session_state.broker.transaction_history)
                # Ensure numeric
                df_h['P&L'] = pd.to_numeric(df_h['P&L'], errors='coerce').fillna(0)
                
                total_fees = df_h['Fee'].sum() + df_h['Tax'].sum()
                total_win = df_h[df_h['P&L'] > 0]['P&L'].sum()
                total_loss = df_h[df_h['P&L'] < 0]['P&L'].sum()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("總手續費+稅", f"{total_fees:,.0f}")
                c2.metric("總獲利交易", f"{total_win:,.0f}")
                c3.metric("總虧損交易", f"{total_loss:,.0f}")
            else:
                    st.info("累積足夠交易後將顯示統計")

    # ==========================================
    # PAGE: AI PREDICTION LAB
    # ==========================================
    elif page == "🧠 AI 預測實驗室":
        from ui_resources import AI_MODEL_EXPLANATION
        
        st.title("🧠 AI 股價預測實驗室")
        st.caption("結合 機器學習 (XGBoost) 與 深度學習 (LSTM) 的混合專家系統")
        
        with st.expander("📖 了解 AI 如何運算 (模型原理說明)", expanded=False):
            st.markdown(AI_MODEL_EXPLANATION)
            
        st.divider()
        
        # --- Sidebar Controls ---
        st.sidebar.header("⚙️ 模型參數設定")
        
        # 2. Comparison Mode (Single or Batch)
        mode = st.sidebar.radio("模式選擇", ["單一股票分析", "批量掃描 (Batch)"], horizontal=True)
        
        target_tickers = []
        
        if mode == "單一股票分析":
            pred_ticker = st.sidebar.text_input("股票代號", value="2330.TW", key="pred_ticker")
            if pred_ticker and pred_ticker.isdigit() and len(pred_ticker) == 4:
                pred_ticker += ".TW"
            target_tickers = [pred_ticker]
        else:
            # Sync with Watchlist
            act_name = st.session_state.get('active_list', 'Default')
            watch_items = st.session_state.watchlists.get(act_name, ["2330.TW"])
            default_list = ", ".join(watch_items)
            
            st.sidebar.caption(f"📋 已載入清單：{act_name} ({len(watch_items)}檔)")
            user_list = st.sidebar.text_area("股票清單 (可手動修改)", value=default_list, height=100)
            
            # Parse list
            raw_list = [x.strip() for x in user_list.replace('\n', ',').split(',')]
            for t in raw_list:
                if t:
                    if t.isdigit() and len(t) == 4: t += ".TW"
                    target_tickers.append(t)
        
        # 3. Parameters
        lookback_years = st.sidebar.slider("訓練資料長度 (年)", 1, 5, 2)
        forecast_days = st.sidebar.slider("預測未來天數 (Days)", 1, 5, 5)
        
        start_text = "🚀 啟動單一分析" if mode == "單一股票分析" else f"🚀 啟動批量掃描 ({len(target_tickers)}檔)"
        start_btn = st.sidebar.button(start_text, type="primary")
        
        if start_btn and target_tickers:
            st.divider()
            
            # Container for all results
            batch_summary = []
            detailed_reports = [] # To store figures and dataframes for sequential rendering
            
            total_stocks = len(target_tickers)
            main_prog = st.progress(0, text=f"開始執行 {total_stocks} 檔股票 AI 預測...")
            
            from prediction_engine import train_xgboost, train_lstm, train_prophet
            
            for idx, ticker in enumerate(target_tickers):
                stock_name = get_stock_name(ticker)
                main_prog.progress((idx) / total_stocks, text=f"正在分析 ({idx+1}/{total_stocks}): {ticker} {stock_name} ...")
                
                try:
                    # 1. Data Prep
                    feature_df = prepare_data(ticker, period=f"{lookback_years}y")
                    
                    if feature_df.empty:
                        st.warning(f"⚠️ {ticker} 無法取得數據，跳過。")
                        continue
                        
                    last_close = float(feature_df['Close'].iloc[-1])
                    last_date = feature_df.index[-1]
                    
                    # 2. XGBoost
                    xgb_predictions = []
                    # Enhanced Feature Set
                    features = ['Close', 'MA5', 'MA20', 'RSI', 'MACD', 'MACD_Hist', 'K', 'D', 'UpperB', 'LowerB', 'PctChange', 'VolChange', 'VIX']
                    latest_features = feature_df.iloc[-1:][features]
                    
                    for d in range(1, forecast_days + 1):
                        model_x, results_x, mae_x, rmse_x, mape_x, f_imp_x = train_xgboost(feature_df, horizon=d)
                        
                        # Capture T+1 Backtest Data for Visualization
                        if d == 1:
                            backtest_xgb = results_x
                            
                        next_pred = model_x.predict(latest_features)[0]
                        conf_score = max(0, 100 * (1 - mape_x))
                        xgb_predictions.append({"Day": f"T+{d}", "Price": next_pred, "Conf": conf_score, "MAE": mae_x, "Imp": f_imp_x})
                        
                    # 3. LSTM
                    model_l, results_l, mae_l, rmse_l, mape_l, future_prices_l, history_l = train_lstm(
                        feature_df, forecast_days=forecast_days, seq_length=60, epochs=10
                    )
                    
                    # 4. Prophet (NEW)
                    prophet_forecast, future_prices_p, model_p, mae_p = train_prophet(feature_df, forecast_days=forecast_days)
                    
                    # --- Aggregate T+1 Results ---
                    t1_xgb = xgb_predictions[0]['Price']
                    t1_lstm = future_prices_l[0]
                    t1_prophet = future_prices_p[0] # Prophet T+1
                    
                    avg_pred = (t1_xgb + t1_lstm + t1_prophet) / 3
                    change_val = avg_pred - last_close
                    change_pct = (change_val / last_close) * 100
                    
                    # Store Summary
                    batch_summary.append({
                        "代號": ticker,
                        "名稱": stock_name,
                        "收盤價": last_close,
                        "XGBoost": round(t1_xgb, 2),
                        "LSTM": round(t1_lstm, 2),
                        "Prophet": round(t1_prophet, 2),
                        "平均預測": round(avg_pred, 2),
                        "Change%": change_pct
                    })
                    
                    # 5. Prepare Detailed Visualization (Store for later rendering)
                    
                    # Consolidated Data for Table
                    comp_data = []
                    for i in range(forecast_days):
                         xp = xgb_predictions[i]['Price']
                         lp = future_prices_l[i]
                         pp = future_prices_p[i]
                         ap = (xp + lp + pp) / 3
                         comp_data.append({
                             "Day": f"T+{i+1}",
                             "XGB": f"{xp:.1f}",
                             "LSTM": f"{lp:.1f}",
                             "Prophet": f"{pp:.1f}",
                             "Avg": f"{ap:.1f}",
                             "Chg%": f"{((ap-last_close)/last_close)*100:+.2f}%"
                         })

                    # Chart Data
                    fig = go.Figure()
                    
                    # History (Last 90 days)
                    hist_data = feature_df.iloc[-90:]
                    fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'], name='歷史股價', line=dict(color='gray', width=2)))
                    
                    # Future Dates
                    future_dates = [last_date + datetime.timedelta(days=i) for i in range(1, forecast_days+1)]
                    
                    # XGB Line
                    xgb_line = [p['Price'] for p in xgb_predictions]
                    fig.add_trace(go.Scatter(x=future_dates, y=xgb_line, name='XGB (技術)', line=dict(color='#00CC96', width=3, dash='dot')))
                    
                    # LSTM Line
                    lstm_line = future_prices_l
                    fig.add_trace(go.Scatter(x=future_dates, y=lstm_line, name='LSTM (趨勢)', line=dict(color='#EF553B', width=3)))
                    
                    # Prophet Line
                    prophet_line = future_prices_p
                    fig.add_trace(go.Scatter(x=future_dates, y=prophet_line, name='Prophet (週期)', line=dict(color='#AB63FA', width=3, dash='dash')))

                    fig.update_layout(title=f"{ticker} {stock_name} - 三大 AI 模型預測走勢", template="plotly_dark", height=400)
                    
                    # Collect Metrics
                    metrics = {
                        "MAE_XGB": xgb_predictions[0]['MAE'],
                        "MAE_LSTM": mae_l,
                        "MAE_Prophet": mae_p
                    }

                    detailed_reports.append({
                        "ticker": ticker,
                        "name": stock_name,
                        "change_pct": change_pct, # Key for sorting
                        "fig": fig,
                        "comp_df": pd.DataFrame(comp_data),
                        "loss_history": history_l.history['loss'] if history_l else [],
                        "mape_x": mape_x,
                        "mape_l": mape_l,
                        "f_imp": xgb_predictions[0]['Imp'], # Added Feature Importance
                        "prophet_model": model_p,
                        "prophet_forecast": prophet_forecast,
                        "backtest_xgb": backtest_xgb,
                        "backtest_lstm": results_l
                    })
                    
                except Exception as e:
                    st.error(f"Error analyzing {ticker}: {e}")
            
            main_prog.progress(100, text="✅ 分析完成！正在生成報告...")
            
            # --- RENDER SECTION ---
            
            if batch_summary:
                # 1. Leaderboard
                st.header("🏆 AI 潛力股排行榜 (Leaderboard)")
                st.caption("依據 T+1 預測漲幅由高至低排序")
                
                summary_df = pd.DataFrame(batch_summary)
                summary_df = summary_df.sort_values(by="Change%", ascending=False).reset_index(drop=True)
                
                # Formatting
                st.dataframe(
                    summary_df.style.format({
                        "Current": "{:.1f}",
                        "XGB T+1": "{:.1f}",
                        "LSTM T+1": "{:.1f}",
                        "Avg T+1": "{:.1f}",
                        "Change%": "{:+.2f}%",
                        "Conf(Avg)": "{:.0f}%"
                    }).background_gradient(subset=['Change%'], cmap='RdYlGn'),
                    use_container_width=True
                )
                
                st.divider()
                
                # 2. Detailed Reports (Sorted)
                st.header("📉 個股詳細分析 (Detailed Reports)")
                
                # Sort reports list by change_pct desc
                detailed_reports.sort(key=lambda x: x['change_pct'], reverse=True)
                
                for report in detailed_reports:
                    with st.expander(f"📊 {report['ticker']} {report['name']} | 預測漲幅: {report['change_pct']:+.2f}%", expanded=len(detailed_reports)==1):
                        c1, c2 = st.columns([2, 1])
                        
                        with c1:
                            st.plotly_chart(report['fig'], use_container_width=True)
                        
                        with c2:
                            st.write("##### 每日預測數據")
                            st.dataframe(report['comp_df'], hide_index=True)
                            
                            st.write("##### 模型誤差 (MAPE)")
                            st.write(f"XGB: {report['mape_x']*100:.1f}% | LSTM: {report['mape_l']*100:.1f}%")
                            
                            if report['loss_history']:
                                st.area_chart(report['loss_history'], height=100, color='#888888')
                                st.caption("LSTM Training Loss")

                        # --- Feature Importance ---
                        if 'f_imp' in report:
                            st.markdown("🔑 **XGBoost 決策關鍵因子**")
                            imp_df = pd.DataFrame(list(report['f_imp'].items()), columns=['Feature', 'Importance'])
                            imp_df = imp_df.sort_values(by='Importance', ascending=True)
                            fig_imp = px.bar(imp_df, x='Importance', y='Feature', orientation='h', height=300, template="plotly_dark")
                            st.plotly_chart(fig_imp, use_container_width=True)

                        # --- Prophet Components ---
                        st.write("🔮 **Prophet 週期性分析 (趨勢/週效應/年效應)**")
                        try:
                            from prophet.plot import plot_components_plotly
                            if 'prophet_model' in report:
                                fig_comp = plot_components_plotly(report['prophet_model'], report['prophet_forecast'])
                                fig_comp.update_layout(height=600, template="plotly_dark")
                                st.plotly_chart(fig_comp, use_container_width=True)
                        except:
                            st.warning("無法繪製 Prophet 組件圖")

                        # --- Backtest Visualization (NEW) ---
                        st.divider()
                        st.markdown("📉 **模型回測驗證 (過去 90 天準確度)**")
                        st.caption("此圖顯示模型對「過去股價」的預測能力 (白線:實際, 虛線:預測)。")
                        
                        bt_fig = go.Figure()
                        
                        # 1. Actual Price (from XGB test set)
                        if 'backtest_xgb' in report:
                            bx = report['backtest_xgb']
                            if not bx.empty:
                                bx = bx.tail(90) # Limit to last 90 days
                                bt_fig.add_trace(go.Scatter(x=bx.index, y=bx['Actual'], name='實際股價 (Actual)', line=dict(color='white', width=2)))
                                bt_fig.add_trace(go.Scatter(x=bx.index, y=bx['Predicted'], name='XGB 預測', line=dict(color='#00CC96', width=1, dash='dot')))
                                
                        # 2. LSTM (Self-Check)
                        if 'backtest_lstm' in report:
                            bl = report['backtest_lstm']
                            # Note: bl might be dataframe or list depending on how train_lstm returned it
                            # train_lstm returns 'results' dataframe with 'Predicted' column
                            if isinstance(bl, pd.DataFrame) and not bl.empty:
                                bl = bl.tail(90) # Limit to last 90 days
                                bt_fig.add_trace(go.Scatter(x=bl.index, y=bl['Predicted'], name='LSTM 預測', line=dict(color='#EF553B', width=1, dash='dot')))

                        # 3. Prophet (History Fit) 
                        if 'prophet_forecast' in report:
                            bp = report['prophet_forecast']
                            # Filter to last 90 days
                            cutoff = datetime.datetime.now()
                            bp_hist = bp[bp['ds'] < cutoff].tail(90)
                            bt_fig.add_trace(go.Scatter(x=bp_hist['ds'], y=bp_hist['yhat'], name='Prophet 擬合', line=dict(color='#AB63FA', width=1, dash='dash')))

                        bt_fig.update_layout(title="AI 模型回測 vs 實際走勢", template="plotly_dark", height=400)
                        st.plotly_chart(bt_fig, use_container_width=True)
                                
            else:
                st.warning("沒有成功產生的預測結果。")
    elif page == "📚 使用指南":
        st.markdown(MANUAL_TEXT)

    # Sidebar: Management (Global)
    with st.sidebar.expander("⚙️ 管理與新增"):
        t_pop, t_man, t_lst = st.tabs(["熱門", "輸入", "清單"])
        with t_pop:
             # Use helper for display
             pop_opts = list(STOCK_NAMES.keys())
             sel_pop = st.selectbox("選擇熱門股", pop_opts, format_func=lambda x: f"{x} {STOCK_NAMES[x]}")
             if st.button("加入"):
                 ticker_code = sel_pop if ".TW" in sel_pop else sel_pop+".TW"
                 if ticker_code not in codes:
                     st.session_state.watchlists[act_list].append(ticker_code); persist(); st.toast(f"已加入 {ticker_code}"); st.rerun()
        with t_man:
             manual_in = st.text_input("輸入代碼", key="manual_add").strip().upper()
             if st.button("加入代碼"):
                 if manual_in:
                     if manual_in.isdigit(): manual_in += ".TW"
                     if manual_in not in codes:
                         st.session_state.watchlists[act_list].append(manual_in); persist(); st.toast(f"已加入 {manual_in}"); st.rerun()
        with t_lst:
             new_list_name = st.text_input("新清單名", key="new_list").strip()
             if st.button("建立"):
                 if new_list_name and new_list_name not in st.session_state.watchlists:
                     st.session_state.watchlists[new_list_name] = []; st.session_state.active_list = new_list_name; persist(); st.rerun()
             if st.button("刪除目前的清單"):
                 if len(st.session_state.watchlists) > 1:
                     del st.session_state.watchlists[act_list]; st.session_state.active_list = list(st.session_state.watchlists.keys())[0]; persist(); st.rerun()

    # ==========================================
    # BOT EXECUTION LOOP (Global)
    # ==========================================


    # ==========================================
    # PAGE: BOT
    # ==========================================
    if page == "🤖 智能機器人":
        st.markdown("### 💰 量化帳戶")
        acc = st.session_state.broker.get_account_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("總資產", f"${acc['Total_Assets']/10000:.1f}萬")
        c2.metric("現金", f"${acc['Balance']/10000:.1f}萬")
        c3.metric("未實現損益", f"${acc['Unrealized_PnL']:,.0f}", delta_color="inverse")
        
        # --- Logic Documentation ---
        with st.expander("📖 機器人運作邏輯說明 (點此展開)", expanded=False):
            st.markdown("""
            **1. 自動買入機制 (Buy Logic)**
            *   **觸發條件**: 策略出現「買進訊號 (Signal 1)」且現金足夠。
            *   **買入數量**: 依照下方您為每檔股票設定的「每次買入張數」執行 (預設 1 張)。
            *   **安全限制**: 若買入後會超過「單檔資金上限」，則不會執行。

            **2. 自動賣出機制 (Sell Logic)**
            *   **觸發條件**: 策略出現「賣出訊號 (Signal -1)」或「觸發停損/停利」。
            *   **賣出數量**: **全數出清** (機器人會將該股票的庫存一次賣光)。

            **3. 風險控管 (Risk Mgmt)**
            *   優先權高於策略訊號。一旦觸發停損或停利，將強制平倉。
            """)
            
        st.divider()
        
        c_set, c_ctrl = st.columns([0.4, 0.6])
        with c_set:
            st.subheader("⚙️ 監控與參數")
            sl = st.number_input("停損 %", value=st.session_state.bot_config.get('sl_pct', 10.0))
            tp = st.number_input("停利 %", value=st.session_state.bot_config.get('tp_pct', 20.0))
            cap = st.number_input("單檔上限", value=st.session_state.bot_config.get('cap_limit_per_stock', 1000000))
            
            watch_items = st.session_state.watchlists[st.session_state.active_list]
            current_targets = st.session_state.bot_config.get('targets', [])
            # Ensure buy_qty dict exists
            if 'buy_qty' not in st.session_state.bot_config:
                st.session_state.bot_config['buy_qty'] = {}
            
            # --- UI Design: Separate ADD and REMOVE ---
            
            with st.expander("➕ 新增監控 (從目前自選股)", expanded=True):
                # Only show items NOT already in targets to avoid confusion
                add_opts = [x for x in watch_items if x not in current_targets]
                to_add = st.multiselect("選擇加入", add_opts, format_func=lambda x: f"{x} {get_stock_name(x)}")
                # Custom Qty Input
                add_qty = st.number_input("每次買進張數", min_value=1, value=1, key="add_qty_input")
                
                if st.button("加入監控"):
                    if to_add:
                        # Append and Dedup
                        new_list = list(set(current_targets + to_add))
                        st.session_state.bot_config['targets'] = new_list
                        # Set Qty
                        for t in to_add:
                            st.session_state.bot_config['buy_qty'][t] = add_qty * 1000
                        persist()
                        st.success(f"已加入 {len(to_add)} 檔 (每檔 {add_qty} 張)")
                        st.rerun()
                        
            with st.expander("✏️ 管理/移除監控", expanded=True):
                # Select ONE to edit detailed settings
                target_to_edit = st.selectbox("選擇要管理/移除的股票", ["(請選擇)"] + current_targets, format_func=lambda x: f"{x} {get_stock_name(x)}" if x != "(請選擇)" else x)
                
                if target_to_edit != "(請選擇)":
                    curr_q = st.session_state.bot_config['buy_qty'].get(target_to_edit, 1000)
                    curr_s = st.session_state.bot_config.get('strategies', {}).get(target_to_edit, "MA_Cross")
                    
                    c_e1, c_e2 = st.columns(2)
                    new_q = c_e1.number_input(f"修改 {target_to_edit} 買進張數", min_value=1, value=int(curr_q/1000))
                    if c_e1.button("更新張數"):
                        st.session_state.bot_config['buy_qty'][target_to_edit] = new_q * 1000
                        persist()
                        st.success("已更新")
                        
                    if c_e2.button(f"🗑️ 停止監控 {target_to_edit}"):
                        new_list = [x for x in current_targets if x != target_to_edit]
                        st.session_state.bot_config['targets'] = new_list
                        persist()
                        st.success("已移除")
                        st.rerun()

            st.markdown("---")
            if st.button("💾 儲存全域參數 (風控/金額)"):
                 st.session_state.bot_config.update({'cap_limit_per_stock': cap, 'sl_pct': sl, 'tp_pct': tp})
                 persist(); st.success("參數已更新")
        with c_ctrl:
            st.subheader("📡 運行控制")
            if st.session_state.get('bot_active'):
                st.info(f"🟢 機器人運行中 (Loop: {st.session_state.get('last_run_count', 0)})")
                if st.button("⏹️ 停止"): st.session_state.bot_active=False; persist(); st.rerun()
            else:
                st.error("🔴 已停止")
                if st.button("▶️ 啟動"): st.session_state.bot_active=True; persist(); st.rerun()
                
        if st.button("🚀 執行策略最佳化"):
            prog = st.progress(0)
            best_map = {}
            strats = ["MA_Cross", "RSI_Strategy", "MACD_Strategy", "KD_Strategy", "Bollinger_Strategy"]
            
            # Use current targets from session state
            opt_targets = st.session_state.bot_config.get('targets', [])
            
            for i, s_code in enumerate(opt_targets):
                b_ret = -999; b_strat = "MA_Cross"
                df = get_stock_data(s_code, period="1y")
                if not df.empty:
                    for strat_n in strats:
                        e = BacktestEngine(1000000); eq, tr = e.run_backtest(df, strat_n); kp = e.calculate_kpis(eq, tr)
                        if kp['Total Return'] > b_ret: b_ret = kp['Total Return']; b_strat = strat_n
                best_map[s_code] = b_strat
                prog.progress((i+1)/len(opt_targets))
            st.session_state.bot_config['strategies'] = best_map; persist(); st.success("Optimized")

        st.write("狀態:")
        rows = []
        targets = st.session_state.bot_config.get('targets', [])
        strategies = st.session_state.bot_config.get('strategies', {})
        buy_qtys = st.session_state.bot_config.get('buy_qty', {})
        
        for t in targets:
            strat = strategies.get(t, "MA_Cross")
            qty_set = buy_qtys.get(t, 1000)
            df_stat = get_stock_data(t, period="6mo")
            
            if not df_stat.empty:
                df_stat = calculate_indicators(df_stat)
                
            st_txt = get_strategy_status(df_stat, strat)
            curr = 0; t_str = "-"
            if not df_stat.empty:
                curr = df_stat['Close'].iloc[-1]
                t_str = df_stat.index[-1].strftime("%Y-%m-%d %H:%M") # FORMAT CHANGED
            else:
                curr = get_latest_price(t)
                
            rows.append({
                "股票": t, 
                "名稱": get_stock_name(t), 
                "策略": strat, 
                "設定張數": f"{qty_set/1000:.0f} 張",
                "現價": f"{curr:.2f}", 
                "資料時間": t_str, 
                "建議": st_txt
            })
        st.dataframe(pd.DataFrame(rows))

    # ==========================================
    # PAGE: BACKTEST
    # ==========================================
    elif page == "🔬 回測實驗室":
        st.header("🔬 回測")
        # Format func
        t = st.selectbox("標的", st.session_state.watchlists[st.session_state.active_list], format_func=lambda x: f"{x} {get_stock_name(x)}")
        s = st.selectbox("策略", ["MA_Cross", "RSI_Strategy", "MACD_Strategy", "KD_Strategy", "Bollinger_Strategy"])
        if st.button("Run"):
            with st.spinner("Backtesting..."):
                df=get_stock_data(t,period="2y")
                if not df.empty:
                    e=BacktestEngine(1000000)
                    eq,tr=e.run_backtest(df,s)
                    k=e.calculate_kpis(eq,tr)
            
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("報酬", f"{k.get('Total Return', 0):.1f}%")
                    k2.metric("勝率", f"{k.get('Win Rate', 0):.1f}%")
                    k3.metric("MDD", f"{k.get('MDD', 0):.1f}%")
                    k4.metric("次數", f"{k.get('Total Trades', 0)}")
                    
                    if not eq.empty:
                        st.plotly_chart(px.line(eq,y='Equity'))
                    if not tr.empty:
                        st.dataframe(tr)
                else:
                    st.error("無法取得歷史數據")

    # ==========================================
    # BOT EXECUTION LOOP (Moved to End for Non-Blocking UI)
    # ==========================================
    if st.session_state.get("bot_active", False):
        # Only run if count updated (throttling)
        # Note: 'count' variable is from st_autorefresh at top of function
        running_needed = False
        if "last_run_count" not in st.session_state: st.session_state.last_run_count = -1
        if count > st.session_state.last_run_count:
            running_needed = True
            st.session_state.last_run_count = count
            
        if running_needed:
            # Status Indicator for user feedback without blocking early render
            with st.status("🤖 機器人掃描市場中...", expanded=False) as status:
                targets = st.session_state.bot_config.get('targets', [])
                cap_limit = st.session_state.bot_config.get('cap_limit_per_stock', 1000000)
                sl_pct = st.session_state.bot_config.get('sl_pct', 10.0) / 100.0
                tp_pct = st.session_state.bot_config.get('tp_pct', 20.0) / 100.0
                
                for symbol in targets:
                    status.write(f"正在分析 {symbol}...")
                    strat = st.session_state.bot_config.get('strategies', {}).get(symbol, "MA_Cross")
                    try:
                        df_bot = get_stock_data(symbol, period="6mo")
                        if not df_bot.empty:
                            df_bot = calculate_indicators(df_bot)
                            curr_row = df_bot.iloc[-1]
                            prev_row = df_bot.iloc[-2]
                            
                            sig = get_signal(curr_row, prev_row, strat)
                            # Get Price safely
                            current_price = float(curr_row['Close'])

                            inv = st.session_state.broker.inventory.get(symbol, {'qty': 0, 'cost': 0})
                            curr_qty = inv['qty']
                            avg_cost = inv['cost']
                            
                            executed = False
                            msg = ""
                            
                            # SL/TP Check
                            if curr_qty != 0:
                                 if curr_qty > 0: pnl_pct = (current_price - avg_cost) / avg_cost
                                 else: pnl_pct = (avg_cost - current_price) / avg_cost
                                 
                                 if pnl_pct < -sl_pct:
                                      s, m = st.session_state.broker.sell(symbol, current_price, abs(curr_qty), action="現股賣出") if curr_qty > 0 else st.session_state.broker.buy(symbol, current_price, abs(curr_qty), action="融券回補")
                                      if s: msg=f"🛡️ 觸發停損 ({pnl_pct*100:.1f}%)! 強制平倉 {symbol}: {m}"; executed=True
                                 elif pnl_pct > tp_pct:
                                      s, m = st.session_state.broker.sell(symbol, current_price, abs(curr_qty), action="現股賣出") if curr_qty > 0 else st.session_state.broker.buy(symbol, current_price, abs(curr_qty), action="融券回補")
                                      if s: msg=f"💰 觸發停利 ({pnl_pct*100:.1f}%)! 強制平倉 {symbol}: {m}"; executed=True

                            # Strategy Signal Check
                            if not executed:
                                if sig == 1: # Buy
                                    custom_qty = st.session_state.bot_config.get('buy_qty', {}).get(symbol, 1000)
                                    exposure = curr_qty * current_price
                                    if (cap_limit - exposure) > current_price * custom_qty:
                                        s, m = st.session_state.broker.buy(symbol, current_price, custom_qty, action="現股買進")
                                        if s: msg=f"🤖 Bot買進 {symbol} ({strat}): {m}"; executed=True
                                elif sig == -1: # Sell
                                    if curr_qty > 0:
                                        s, m = st.session_state.broker.sell(symbol, current_price, curr_qty, action="現股賣出")
                                        if s: msg=f"🤖 Bot賣出 {symbol} ({strat}): {m}"; executed=True
                            
                            if executed:
                                st.toast(msg, icon="🔔")
                                st.session_state.trade_log.append(f"[{datetime.datetime.now()}] {msg}")
                                persist()
                    except Exception as e:
                        print(f"Bot Error {symbol}: {e}")
                        pass
                status.update(label="🤖 掃描完成", state="complete", expanded=False)

# --- Entry Point ---
if st.session_state.get('logged_in'):
    # Initialize User Data if first load for this user
    if "data_loaded_user" not in st.session_state or st.session_state.data_loaded_user != st.session_state.username:
        data = load_data(st.session_state.username)
        # Restore State Logic (Simplified copy from old init)
        st.session_state.broker = PaperBroker(initial_balance=10000000) # Reset then load
        
        if data:
            st.session_state.broker.restore_state(
                data.get("balance", 10000000), 
                data.get("inventory", {}), 
                data.get("transaction_history", [])
            )
            st.session_state.watchlists = data.get("watchlists", {
                "我的自選股": ["2330.TW", "2317.TW"], 
                "高股息": ["0056.TW", "00878.TW"]
            })
            st.session_state.trade_log = data.get("trade_log", [])
            # Config Merge
            loaded_conf = data.get("bot_config", {})
            default_conf = {"targets": [], "cap_limit_per_stock": 1000000, "strategies": {}, "sl_pct": 10.0, "tp_pct": 20.0, "buy_qty": {}}
            if not loaded_conf: loaded_conf = default_conf
            else:
                 for k, v in default_conf.items():
                     if k not in loaded_conf: loaded_conf[k] = v
                 if 'buy_qty' not in loaded_conf: loaded_conf['buy_qty'] = {}
            st.session_state.bot_config = loaded_conf
        else:
             # Fresh User Defaults
             st.session_state.watchlists = {"我的自選股": []}
             st.session_state.bot_config = {"targets": [], "cap_limit_per_stock": 1000000, "strategies": {}, "sl_pct": 10.0, "tp_pct": 20.0, "buy_qty": {}}
             st.session_state.trade_log = []
             
        st.session_state.active_list = list(st.session_state.watchlists.keys())[0] if st.session_state.watchlists else "我的自選股"
        st.session_state.data_loaded_user = st.session_state.username

    main_app()
else:
    render_login_ui()
