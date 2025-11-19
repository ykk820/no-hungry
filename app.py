import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse
import time

# ==========================================
# 1. 系統全域設定 (請確保這段是正確的)
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbwZsrOvS7QrNTaXVcJo1L7HZpmcUSvjZg6JPOPjPbW5-9EYzRUzVYxVs0K--Tp93DxhKQ/exec"
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"
BASE_APP_URL = "https://no-hungry.streamlit.app" # 你的 APP 網址

# ==========================================
# 2. 資料庫連線函式 (保持不變)
# ==========================================
def get_client():
    try:
        if "gcp_service_account" not in st.secrets: return None
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except: return None

@st.cache_data(ttl=10)
def load_data():
    """讀取店家設定(含地區) & 領取紀錄"""
    client = get_client()
    if not client: return {}, []
    
    try:
        ss = client.open_by_key(SPREADSHEET_ID)
        
        # 1. 讀取店家
        try:
            ws_shops = ss.worksheet("店家設定")
            raw_shops = ws_shops.get_all_records()
            shops_db = {}
            for row in raw_shops:
                name = str(row.get('店名', '')).strip()
                if name:
                    shops_db[name] = {
                        'region': str(row.get('地區', '未分類')), 
                        'lat': float(row.get('緯度', 0) or 0),
                        'lon': float(row.get('經度', 0) or 0),
                        'item': str(row.get('商品', '優惠商品')),
                        'price': int(row.get('價格', 0) or 0),
                        'stock': int(row.get('初始庫存', 0) or 0)
                    }
        except: shops_db = {}

        # 2. 讀取訂單
        try:
            ws_orders = ss.worksheet("領取紀錄")
            orders = ws_orders.get_all_records()
        except: orders = []

        return shops_db, orders
    except: return {}, []

def delete_order(idx):
    client = get_client()
    if client:
        try:
            client.open_by_key(SPREADSHEET_ID).worksheet("領取紀錄").delete_rows(idx + 2)
            return True
        except: return False
    return False

# ==========================================
# 3. 頁面開始
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱", layout="wide")

SHOPS_DB, ALL_ORDERS = load_data()
ORDERS_DF = pd.DataFrame(ALL_ORDERS)

params = st.query_params
current_mode = params.get("mode", "consumer")
shop_target = params.get("name", None)

# --- 商家後台模式 ---
if current_mode == "shop" and shop_target in SHOPS_DB:
    
    # ... (商家後台邏輯，保持不變) ...
    st.title(f"🏪 {shop_target} - 商家後台")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()
        
    shop_info = SHOPS_DB[shop_target]
    
    shop_orders = pd.DataFrame()
    sold = 0
    if not ORDERS_DF.empty:
        shop_orders = ORDERS_DF[ORDERS_DF.apply(lambda x: shop_target in str(x.values), axis=1)]
        sold = len(shop_orders)
    
    remain = shop_info['stock'] - sold
    rev = sold * shop_info['price']
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📦 總庫存", shop_info['stock'])
    c2.metric("✅ 已售出", sold)
    c3.metric("🔥 剩餘", remain, delta_color="inverse")
    c4.metric("💰 營收", f"${rev}")
    
    st.divider()
    st.subheader("📋 現場核銷名單")
    if not shop_orders.empty:
        st.dataframe(shop_orders, use_container_width=True)
    else:
        st.info("目前無待處理訂單")
        
    if st.button("⬅️ 回首頁"):
        st.query_params.clear()
        st.rerun()

# --- 消費者 + 管理員模式 ---
else:
    # --- 側邊欄：管理員 ---
    with st.sidebar:
        st.header("🔒 管理員")
        pwd = st.text_input("密碼", type="password")
        is_admin = (pwd == "ykk8880820")
        
        if is_admin:
            st.success("已登入")
            st.divider()
            
            # 🚀 快速進入商家後台
            st.subheader("🚀 快速進入商家後台")
            target_shop_admin = st.selectbox("選擇要管理的店家", list(SHOPS_DB.keys()))
            if st.button("進入該店後台"):
                st.query_params["mode"] = "shop"
                st.query_params["name"] = target_shop_admin
                st.rerun()
            
            # ... (QR Code 功能保留) ...
            st.divider()
            st.subheader("📱 產生 QR Code")
            qr_shop = st.selectbox("選擇店家 (QR Code)", list(SHOPS_DB.keys()))
            
            shop_link = f"{BASE_APP_URL}/?mode=shop&name={urllib.parse.quote(qr_shop)}"
            st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(shop_link)}")
            st.code(shop_link)
            
            if st.button("清除快取"):
                st.cache_data.clear()
                st.rerun()

    # --- 主畫面 ---
    st.title("🍱 餓不死地圖")
    
    if not SHOPS_DB:
        st.warning("⚠️ 無法讀取店家資料，請檢查 Google Sheet 設定。")
        st.stop()

    # 1. 區域篩選功能
    all_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
    selected_region = st.selectbox("📍 請選擇區域", ["所有區域"] + all_regions)
    
    # 篩選店家
    if selected_region == "所有區域":
        filtered_shops = SHOPS_DB
    else:
        filtered_shops = {k: v for k, v in SHOPS_DB.items() if v['region'] == selected_region}

    # 2. 地圖顯示 (台灣全覽邏輯修正處)
    if filtered_shops:
        map_df = pd.DataFrame([
            {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in filtered_shops.items()
        ])
        
        # 🔴 這裡就是「台灣全覽」的修正處 🔴
        if selected_region == "所有區域":
            map_zoom = 7 # 7 級縮放可看見整個台灣
        else:
            map_zoom = 14 # 特定區域維持高縮放率
            
        st.map(map_df, zoom=map_zoom, use_container_width=True)
    else:
        st.info("該區域目前沒有合作店家。")

    st.divider()

    # 3. 下單與列表 (保持不變)
    c1, c2 = st.columns([1.2, 1])
    
    with c1:
        st.subheader("💰 搶購下單")
        target = st.selectbox("選擇店家", list(filtered_shops.keys()))
        info = filtered_shops[target]
        
        # 計算排隊人數與庫存
        queue_count = 0
        if not ORDERS_DF.empty:
            shop_orders = ORDERS_DF[ORDERS_DF.apply(lambda x: target in str(x.values), axis=1)]
            queue_count = len(shop_orders)
        
        current_stock = info['stock'] - queue_count
        if current_stock < 0: current_stock = 0
        
        # 顯示資訊卡片
        st.info(f"""
        **{target}** ({info['region']})
        
        🍱 商品：**{info['item']}**
        💲 價格：**${info['price']}**
        📦 剩餘：**{current_stock}** 份 (總量 {info['stock']})
        👥 目前排隊：**{queue_count}** 人
        """)
        
        # 導航按鈕
        gmap_url = f"https://www.google.com/maps/search/?api=1&query={info['lat']},{info['lon']}"
        st.link_button("🚗 開啟 Google Map 導航前往", gmap_url)
        
        u_name = st.text_input("輸入您的暱稱")
        
        btn_txt = "🚀 立即排隊搶購"
        btn_state = (current_stock <= 0)
            
        if st.button(btn_txt, type="primary", disabled=btn_state, use_container_width=True):
            if u_name:
                with st.spinner("連線中..."):
                    try:
                        requests.post(GAS_URL, json={'user': u_name, 'item': f"{target} - {info['item']}"})
                        st.balloons()
                        st.success("排隊成功！")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except: st.error("連線失敗")
            else:
                st.warning("請輸入名字")

    with c2:
        st.subheader("📋 即時排隊名單")
        
        if not ORDERS_DF.empty:
            # 根據篩選過濾排隊名單 (Admin模式包含刪除)
            if selected_region != "所有區域":
                display_df = ORDERS_DF[ORDERS_DF.apply(lambda x: target in str(x.values), axis=1)]
                st.caption(f"顯示 {target} 的排隊狀況")
            else:
                display_df = ORDERS_DF
                st.caption("顯示全區排隊狀況")

            if not display_df.empty:
                if is_admin:
                    st.write("🛠️ 管理員操作")
                    del_opts = [f"{i}: {r.get('user','?')} - {r.get('item','?')}" for i, r in display_df.iterrows()]
                    target_del = st.selectbox("刪除訂單", del_opts)
                    if st.button("🗑️ 確認刪除"):
                        idx = int(target_del.split(":")[0])
                        delete_order(idx)
                        st.rerun()
                
                cols = [c for c in display_df.columns if c in ['時間', '姓名', 'user', 'item']]
                st.dataframe(display_df[cols].tail(10), use_container_width=True)
            else:
                st.info("目前這家店沒人排隊")
        else:
            st.info("尚無任何訂單")
