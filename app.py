import streamlit as st
import streamlit.components.v1 as components
import ccxt
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import google.generativeai as genai
from PIL import Image
import time
from datetime import datetime

# --- 1. 網頁基本設定 ---
st.set_page_config(page_title="AI 智慧投資決策平台", page_icon="📈", layout="wide")

# --- 2. 自訂 CSS (含排版修正、黑色文字、防閃爍、側邊欄全白修正) ---
st.markdown("""
<style>
    /* === 左側側邊欄 (深色背景 + 強制全白字) === */
    [data-testid="stSidebar"] {
        background-color: #12141C;
    }
    
    /* 針對側邊欄標題 */
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #FFFFFF !important;
    }
    
    /* 針對普通文字、Label */
    [data-testid="stSidebar"] span, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {
        color: #E0E0E0 !important;
        font-weight: 500;
    }

    /* 強制讓 AI 回答的 Markdown 內容全部變白 */
    [data-testid="stSidebar"] .stMarkdown p, 
    [data-testid="stSidebar"] .stMarkdown li, 
    [data-testid="stSidebar"] .stMarkdown ul,
    [data-testid="stSidebar"] .stMarkdown ol,
    [data-testid="stSidebar"] .stMarkdown strong,
    [data-testid="stSidebar"] .stMarkdown code {
        color: #FFFFFF !important;
    }
    
    /* === 右側主畫面文字 === */
    [data-testid="stMetricValue"] {
        font-size: 26px; font-weight: 800; color: #000000 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 15px; color: #444444 !important; font-weight: 600;
    }
    
    /* 數據框 */
    div[data-testid="stInfo"] {
        background-color: #F0F2F6; border: 1px solid #D1D5DB; color: #000000;
    }
    div[data-testid="stInfo"] p {
        font-size: 16px !important; font-weight: bold !important; color: #000000 !important;
    }

    /* 頁尾 */
    .footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #F0F2F6; color: #666; text-align: center;
        padding: 10px; font-size: 12px; border-top: 1px solid #ddd; z-index: 100;
    }
    
    /* 頂部邊距 */
    .block-container { padding-top: 3rem; padding-bottom: 5rem; }

    /* 防閃爍 */
    .element-container, .stMarkdown, .stMetric {
        opacity: 1 !important; transition: none !important; filter: none !important;
    }
    
    /* Live 呼吸燈動畫 */
    @keyframes pulse {
        0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; }
    }
    .live-indicator {
        display: inline-block; width: 10px; height: 10px;
        background-color: #00AA00; border-radius: 50%;
        margin-right: 5px; animation: pulse 1.5s infinite;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 系統狀態初始化與設定 ---
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "messages" not in st.session_state:
    st.session_state.messages = []

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    ai_status = "✅ 就緒"
    has_key = True
except FileNotFoundError:
    api_key = st.sidebar.text_input("輸入 Gemini API Key:", type="password")
    if api_key:
        genai.configure(api_key=api_key)
        ai_status = "✅ 手動輸入"
        has_key = True
    else:
        ai_status = "⚠️ 無金鑰"
        has_key = False

# --- 4. 數據獲取 (快取連線) ---
@st.cache_resource
def get_exchange():
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    exchange.ssl_verification = False
    return exchange

def fetch_market_data(symbol):
    exchange = get_exchange()
    try:
        ticker = exchange.fetch_ticker(symbol)
        bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return ticker, df
    except Exception:
        return None, pd.DataFrame()

# --- 5. 繪圖函數 ---
def plot_gauge_high_contrast(value, title):
    if value < 20: state, color = "強力賣出", "#FF4444"
    elif value < 40: state, color = "賣出", "#FF8888"
    elif value < 60: state, color = "中立", "#888888"
    elif value < 80: state, color = "買入", "#4488FF"
    else: state, color = "強力買入", "#00CC88"

    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta", value = value, domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': f"<b>{title}</b>", 'font': {'size': 20, 'color': "black", 'family': "Arial Black"}},
        number = {'suffix': f"<br><span style='font-size:0.8em;color:{color};font-weight:bold'>{state}</span>", 'font': {'size': 32, 'color': "black"}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 2, 'tickcolor': "black", 'tickvals': [10, 30, 50, 70, 90], 'ticktext': ["強賣", "賣出", "中立", "買入", "強買"], 'tickfont': {'size': 14, 'color': "black", 'family': "Arial"}},
            'bar': {'color': "rgba(0,0,0,0)"}, 'bgcolor': "white", 'borderwidth': 0,
            'steps': [
                {'range': [0, 20], 'color': "#D32F2F"}, {'range': [20, 40], 'color': "#E57373"},  
                {'range': [40, 60], 'color': "#E0E0E0"}, {'range': [60, 80], 'color': "#64B5F6"},  
                {'range': [80, 100], 'color': "#4DB6AC"}  
            ],
            'threshold': {'line': {'color': "black", 'width': 5}, 'thickness': 0.8, 'value': value}
        }
    ))
    fig.update_layout(height=300, margin=dict(l=30,r=30,t=60,b=20), paper_bgcolor="rgba(0,0,0,0)", font={'color': "black"})
    return fig

# --- 6. 定義即時區塊 Fragment (雲端穩定版) ---
# [修改重點] 將 run_every 放寬為 10 秒，減輕雲端伺服器負擔，避免變成空白
@st.fragment(run_every=10)
def show_live_header(symbol):
    ticker, _ = fetch_market_data(symbol)
    if ticker:
        price_change = ticker['percentage']
        color = "#00AA00" if price_change >= 0 else "#FF0000"
        c1, c2 = st.columns([2, 8])
        with c1: st.title(f"{symbol}")
        with c2: 
            current_time = datetime.now().strftime("%H:%M:%S")
            st.markdown(f"""
            <div style='margin-top: 15px; line-height: 1.5;'>
                <span style='font-size: 36px; font-weight: bold;'>${ticker['last']:,.2f}</span>
                <span style='color:{color}; font-size: 24px; font-weight: bold; margin-left: 10px;'> {price_change:+.2f}%</span>
                <div style='font-size: 12px; color: #888; margin-top: 5px;'>
                    <span class="live-indicator"></span> 即時更新中: {current_time}
                </div>
            </div>
            """, unsafe_allow_html=True)

# [修改重點] 將儀表板重新運算放寬為 30 秒
@st.fragment(run_every=30)
def show_live_analysis(symbol):
    ticker, df = fetch_market_data(symbol)
    if ticker and not df.empty:
        df.ta.rsi(length=14, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.ema(length=20, append=True)
        latest = df.iloc[-1]
        close_price, rsi = latest['close'], latest['RSI_14']
        
        osc_score = 50
        if rsi < 30: osc_score = 90
        elif rsi < 45: osc_score = 70
        elif rsi > 70: osc_score = 10
        elif rsi > 55: osc_score = 30
        
        ma_score = 50
        ma_score += 25 if close_price > latest['SMA_50'] else -25
        ma_score += 25 if close_price > latest['EMA_20'] else -25
        summary_score = (osc_score + ma_score) / 2
        
        st.markdown("### ⚡ 技術分析儀表板 (Technical Ratings)")
        g1, g2, g3 = st.columns(3)
        with g1: 
            st.plotly_chart(plot_gauge_high_contrast(osc_score, "震盪指標"), use_container_width=True)
            st.info(f"RSI (14): {rsi:.2f}") 
        with g2: 
            st.plotly_chart(plot_gauge_high_contrast(summary_score, "總結"), use_container_width=True)
            st.info(f"綜合評分: {summary_score:.0f} / 100")
        with g3: 
            st.plotly_chart(plot_gauge_high_contrast(ma_score, "移動平均"), use_container_width=True)
            trend_msg = "看漲 📈" if close_price > latest['SMA_50'] else "看跌 📉"
            st.info(f"價格 vs SMA(50): {trend_msg}")

        st.markdown("### 📊 24H 統計數據")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("最高價", f"${ticker['high']:,.2f}")
        k2.metric("最低價", f"${ticker['low']:,.2f}")
        k3.metric("成交量", f"{ticker['baseVolume']:,.2f}")
        k4.metric("成交額", f"${ticker['quoteVolume']/1000000:.2f} M")

# ==========================================
#  側邊欄 (導覽選單)
# ==========================================
with st.sidebar:
    st.header("🎛️ 主選單")
    
    page_selection = st.radio("前往頁面", ["📊 戰情首頁", "🧠 AI 投資教練", "🛡️ 詐騙檢測"])
    
    st.divider()
    
    symbol = st.selectbox("監控幣種", ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT'])
    st.markdown(f"**AI 狀態:** <span style='color:#00EEAA'>{ai_status}</span>", unsafe_allow_html=True)

# ==========================================
#  主畫面 (根據側邊欄選單動態切換)
# ==========================================

if page_selection == "📊 戰情首頁":
    show_live_header(symbol)

    # 靜態 TradingView
    tv_symbol = f"BINANCE:{symbol.replace('/', '')}"
    tv_code = f"""
    <div class="tradingview-widget-container">
        <div id="tv_chart"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
        new TradingView.widget({{
        "width": "100%", "height": 600, "symbol": "{tv_symbol}",
        "interval": "60", "timezone": "Asia/Taipei", "theme": "dark",
        "style": "1", "locale": "zh_TW", "toolbar_bg": "#f1f3f6",
        "enable_publishing": false, "container_id": "tv_chart"
        }});
        </script>
    </div>
    """
    components.html(tv_code, height=610)
    st.caption("圖表技術支援：TradingView")

    show_live_analysis(symbol)


elif page_selection == "🧠 AI 投資教練":
    c1, c2 = st.columns([8, 2])
    with c1:
        st.title("🧠 AI 投資教練")
    with c2:
        if st.button("🗑️ 清除對話", key="clear_coach", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
            
    st.markdown(f"目前分析幣種：**{symbol}**")

    chat_container = st.container(height=600)

    for message in st.session_state.messages:
        with chat_