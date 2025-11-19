import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse
import time

# ==========================================
# 1. 系統全域設定
# ==========================================
# 🔴 已更新為你剛剛提供的新網址
GAS_URL = "https://script.google.com/macros/s/AKfycbwZsrOvS7QrNTaXVcJo1L7HZpmcUSvjZg6JPOPjPbW5-9EYzRUzVYxVs0K--Tp93DxhKQ/exec"

# Google Sheet ID (如果你沒換表格，就不用動)
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"

# 你的 APP 網址 (請換成你實際發布後的網址，不然 QR Code 會連不到)
BASE_APP_URL = "https://no-hungry.streamlit.app" 

# ==========================================
# 2. 資料庫連線函式
# ==========================================
def get_client():
    """連線 Google Drive API"""
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except:
        return None

@st.cache_data(ttl=10) # 快取 10 秒，確保庫存更新即時
def load_data_from_sheet():
    """一次讀取兩個分頁：店家設定 & 領取紀錄"""
    client = get_client()
    if not client: return {}, []
    
    try:
        ss = client.open_by_key(SPREADSHEET_ID)
        
        # 1. 讀取店家設定
        try:
            ws_shops = ss.worksheet("店家設定")
            shops_data = ws_shops.get_all_records()
            shops_db = {}
            for row in shops_data:
                name = str(row.get('店名', '')).strip()
                if name:
                    shops_db[name] = {
                        'lat': float(row.get('緯度', 0) or 0),
                        'lon': float(row.get('經度', 0) or 0),
                        'item': str(row.get('商品', '優惠商品')),
                        'price': int(row.get('價格', 0) or 0),
                        'stock': int(row.get('初始庫存', 0) or 0)
                    }
        except:
            shops_db = {}

        # 2. 讀取領取紀錄
        try:
            ws_orders = ss.worksheet("領取紀錄")
            orders_list = ws_orders.get_all_records()
        except:
            orders_list = []

        return shops_db, orders_list
    except:
        return {}, []

def delete_order(row_index):
    """管理員刪除訂單"""
    client = get_client()
    if client:
        try:
            ws = client.open_by_key(SPREADSHEET_ID).worksheet("領取紀錄")
            ws.delete_rows(row_index + 2)
            return True
        except: return False
    return False

# ==========================================
# 3. 頁面初始化
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱", layout="wide")

# 載入所有資料
SHOPS_DB, ALL_ORDERS = load_data_from_sheet()
ORDERS_DF = pd.DataFrame(ALL_ORDERS)

# 處理網址參數
params = st.query_params
current_mode = params.get("mode", "consumer") 
shop_target = params.get("name", None)

# ==========================================
# 🏪 模式 A: 商家後台 (完善版)
# ==========================================
if current_mode == "shop" and shop_target:
    # 如果店家不存在於資料庫
    if shop_target not in SHOPS_DB:
        st.error(f"❌ 找不到店家資料：{shop_target}")
        st.stop()

    shop_info = SHOPS_DB[shop_target]
    
    # 側邊欄 (商家資訊)
    with st.sidebar:
        st.title(f"🏪 {shop_target}")
        st.caption("商家管理後台")
        st.info(f"販售商品：{shop_info['item']}\n\n單價：${shop_info['price']}")
        if st.button("⬅️ 登出 (回首頁)"):
            st.query_params.clear()
            st.rerun()

    st.title("📊 實時銷售看板")
    
    if st.button("🔄 刷新最新訂單"):
        st.cache_data.clear()
        st.rerun()

    # 計算該店家的數據
    shop_orders = pd.DataFrame()
    sold_count = 0
    revenue = 0
    
    if not ORDERS_DF.empty:
        # 篩選屬於這家店的訂單 (比對 item 字串)
        shop_orders = ORDERS_DF[ORDERS_DF.apply(lambda row: shop_target in str(row.values), axis=1)]
        sold_count = len(shop_orders)
        revenue = sold_count * shop_info['price']
    
    remaining = shop_info['stock'] - sold_count
    
    # 1. 數據儀表板
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📦 總庫存量", shop_info['stock'])
    col2.metric("✅ 已售出", sold_count)
    col3.metric("🔥 剩餘庫存", remaining, delta_color="inverse")
    col4.metric("💰 預估營收", f"${revenue}")

    st.divider()

    # 2. 訂單管理列表
    st.subheader("📋 待處理訂單")
    
    if not shop_orders.empty:
        # 顯示簡單表格
        display_cols = [c for c in shop_orders.columns if c in ['時間', '姓名', 'user', 'User', '領取項目', 'item']]
        st.dataframe(shop_orders[display_cols], use_container_width=True)
        st.info("💡 提示：現場核對顧客姓名與下單時間即可出餐。")
    else:
        st.info("🍵 目前尚無新訂單，請稍候。")

# ==========================================
# 🗺️ 模式 B: 消費者 + 管理員 (主頁)
# ==========================================
else:
    # 如果沒讀到店家資料，顯示警告
    if not SHOPS_DB:
        st.warning("⚠️ 無法讀取 '店家設定'，請確認 Google Sheet 設定。")
        # 為了不讓地圖掛掉，給一個假資料
        SHOPS_DB = {'範例店家': {'lat': 25.0330, 'lon': 121.5654, 'item': '載入中', 'price': 0, 'stock': 0}}

    # --- 側邊欄：管理員登入 ---
    with st.sidebar:
        st.header("🔒 管理員登入")
        password = st.text_input("密碼", type="password")
        is_admin = (password == "ykk8880820")
        
        if is_admin:
            st.success("✅ 管理員已登入")
            st.divider()
            st.subheader("📱 產生商家後台 QR Code")
            
            # 產生連結
            target_shop_qr = st.selectbox("選擇店家", list(SHOPS_DB.keys()))
            if target_shop_qr:
                # 網址編碼處理
                link = f"{BASE_APP_URL}/?mode=shop&name={urllib.parse.quote(target_shop_qr)}"
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={urllib.parse.quote(link)}"
                
                st.image(qr_url, caption=f"{target_shop_qr} 後台專用")
                st.code(link)
                
            st.divider()
            if st.button("🗑️ 清除全站快取"):
                st.cache_data.clear()
                st.rerun()

    # --- 主畫面 ---
    st.title("🍱 餓不死地圖 (剩食優惠)")
    
    # 1. 地圖區
    map_data = pd.DataFrame([
        {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in SHOPS_DB.items()
    ])
    st.map(map_data, zoom=13, use_container_width=True)

    st.divider()
    
    # 2. 搶購與排隊區
    c1, c2 = st.columns([1, 1.5])
    
    with c1:
        st.subheader("💰 選擇店家搶購")
        
        # 選單
        selected_shop = st.selectbox("請選擇店家", list(SHOPS_DB.keys()))
        info = SHOPS_DB[selected_shop]
        
        # 計算即時庫存 (前端預估)
        current_sold = 0
        if not ORDERS_DF.empty:
             shop_orders = ORDERS_DF[ORDERS_DF.apply(lambda row: selected_shop in str(row.values), axis=1)]
             current_sold = len(shop_orders)
        
        current_stock = info['stock'] - current_sold
        if current_stock < 0: current_stock = 0

        # 顯示商品卡片
        st.success(f"📍 **{selected_shop}**")
        st.markdown(f"""
        - 🍱 商品：**{info['item']}**
        - 💲 特價：**${info['price']}**
        - 📦 剩餘：**{current_stock}** 份 (總量 {info['stock']})
        """)
        
        # 下單表單
        user_name = st.text_input("您的暱稱", placeholder="例如: Ykk")
        
        # 按鈕狀態控制
        btn_label = "🚀 立即搶購"
        btn_disabled = False
        
        if current_stock <= 0:
            btn_label = "❌ 已售完"
            btn_disabled = True
            st.error("來晚了一步，這家店賣完了！")

        if st.button(btn_label, type="primary", disabled=btn_disabled, use_container_width=True):
            if not user_name:
                st.warning("請輸入名字才能搶購！")
            else:
                with st.spinner("連線確認庫存中..."):
                    try:
                        # 傳送完整商品名稱
                        full_item_name = f"{selected_shop} - {info['item']}"
                        payload = {'user': user_name, 'item': full_item_name}
                        
                        # 呼叫 GAS
                        response = requests.post(GAS_URL, json=payload)
                        
                        if response.status_code == 200:
                            res = response.json()
                            if res.get("result") == "success":
                                st.balloons()
                                st.success(f"{res.get('message')}")
                                st.cache_data.clear() # 強制刷新
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"{res.get('message')}") # 顯示限購錯誤
                        else:
                            st.error("連線失敗，請重試。")
                    except Exception as e:
                        st.error(f"發生錯誤: {e}")

    with c2:
        st.subheader("📋 目前排隊狀態")
        
        if not ORDERS_DF.empty:
            # 顯示最近 10 筆
            cols = [c for c in ORDERS_DF.columns if c in ['時間', '姓名', 'user', 'User', '領取項目', 'item', '狀態']]
            
            # 管理員可以看到刪除按鈕
            if is_admin:
                st.write("🔧 **訂單管理 (管理員)**")
                del_list = [f"{i}: {r.get('user', r.get('姓名','?'))} - {r.get('item','?')}" for i, r in ORDERS_DF.iterrows()]
                target_del = st.selectbox("選擇刪除訂單", del_list)
                
                if st.button("🗑️ 刪除此單"):
                    idx = int(target_del.split(":")[0])
                    if delete_order(idx):
                        st.success("已刪除")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("刪除失敗")
                st.dataframe(ORDERS_DF, use_container_width=True)
            else:
                # 一般人只看列表
                st.dataframe(ORDERS_DF[cols].tail(10), use_container_width=True)
        else:
            st.info("目前還沒有人排隊，快來搶頭香！")
