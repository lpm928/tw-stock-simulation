import streamlit as st
import datetime
import time
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
from utils import fetch_twse_institutional_data, get_stock_data, get_latest_price, get_realtime_quote
from broker import PaperBroker
from strategy import check_strategy, calculate_indicators, get_signal, get_strategy_status
from backtest import BacktestEngine
from data_manager import save_data, load_data
from stock_map import get_stock_name, STOCK_NAMES
from ui_resources import ST_STYLE, MANUAL_TEXT
from auth import render_login_ui

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
    # 1. Auto-refresh
    count = st_autorefresh(interval=30000, key="datarefresh")
    
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
    page = st.sidebar.radio("功能導覽", ["🖥️ 模擬操盤室", "🤖 智能機器人", "🔬 回測實驗室", "📚 使用指南"], index=0)

    # ==========================================
    # PAGE: TRADING ROOM (Merged Dashboard, Analysis, Portfolio)
    # ==========================================
    if page == "🖥️ 模擬操盤室":
        st.title("🖥️ 台股模擬操盤室")
        
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
    # PAGE: MANUAL
    # ==========================================
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
