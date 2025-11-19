import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse
import time
import uuid # 引入 UUID 庫來生成唯一ID

# ==========================================
# 0. 設置唯一身份識別碼 (UUID)
# ==========================================
# 每個使用者訪問時，如果 session_state 中沒有 ID，則生成一個新的 UUID。
# 這個 ID 將作為限購和黑名單的依據。
if 'user_uuid' not in st.session_state:
    st.session_state['user_uuid'] = str(uuid.uuid4())

# ==========================================
# 1. 系統全域設定 (不變)
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbz0ltqrGDA1nwXoqchQ-bTHNIW5jDt5OesfcWs6NNLgb-H2p6t6sM3ikxQZVr11arHtyg/exec"
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"
BASE_APP_URL = "https://no-hungry.streamlit.app"

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
                        'mode': str(row.get('模式', '剩食')).strip(),
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

def add_shop_to_backend(data):
    data['action'] = 'add_shop'
    try:
        response = requests.post(GAS_URL, json=data)
        if response.status_code == 200:
            return response.json()
        return {"result": "error", "message": f"連線失敗 (HTTP {response.status_code})"}
    except Exception as e:
        return {"result": "error", "message": f"網路錯誤: {str(e)}"}

# ==========================================
# 3. 頁面開始
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱", layout="wide")

SHOPS_DB, ALL_ORDERS = load_data()
ORDERS_DF = pd.DataFrame(ALL_ORDERS)

params = st.query_params
current_mode = params.get("mode", "consumer")
shop_target = params.get("name", None)

# --- 商家後台模式 (A) --- (保持不變)
if current_mode == "shop" and shop_target in SHOPS_DB:
    
    shop_info = SHOPS_DB[shop_target]
    is_queue_mode = shop_info.get('mode') == '排隊'
    
    with st.sidebar:
        st.title(f"🏪 {shop_target}")
        if st.button("⬅️ 登出 (回首頁)"):
            st.query_params.clear()
            st.rerun()

    st.title(f"📊 實時銷售看板 - {shop_target}")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

    shop_orders = pd.DataFrame()
    sold_or_queued = 0
    if not ORDERS_DF.empty:
        shop_orders = ORDERS_DF[ORDERS_DF.apply(lambda row: shop_target in str(row.values), axis=1)]
        sold_or_queued = len(shop_orders)
    
    c1, c2, c3 = st.columns(3)
    if is_queue_mode:
        c1.metric("👥 總叫號人數", sold_or_queued)
        c2.metric("📋 目前隊伍長度", sold_or_queued)
        c3.metric("💡 模式", "排隊叫號中")
    else:
        remain = shop_info['stock'] - sold_or_queued
        rev = sold_or_queued * shop_info['price']
        c1.metric("📦 總庫存", shop_info['stock'])
        c2.metric("✅ 已售出", sold_or_queued)
        c3.metric("🔥 剩餘", remain, delta_color="inverse")
    
    st.divider()
    st.subheader("📋 待處理名單")
    
    if not shop_orders.empty:
        shop_orders['號碼牌'] = range(1, len(shop_orders) + 1)
        st.dataframe(shop_orders[['號碼牌', '時間', 'user', 'item']], use_container_width=True)
    else:
        st.info("目前無待處理訂單")

# --- 消費者 + 管理員模式 (B) ---
else:
    # --- 側邊欄：管理員 (新增店家表單) ---
    with st.sidebar:
        st.header("🔒 管理員")
        password = st.text_input("密碼", type="password")
        is_admin = (password == "ykk8880820")
        
        if is_admin:
            st.success("已登入")
            st.divider()
            
            # 🚀 🆕 一鍵新增店家表單
            st.subheader("➕ 一鍵新增店家 (自動定位)")
            with st.form("add_shop_form"):
                col_a, col_b = st.columns(2)
                with col_a:
                    new_shop_name = st.text_input("店名*", key="new_shop_name")
                    new_item = st.text_input("商品名*", key="new_item", value="剩食套餐")
                    new_price = st.number_input("價格*", min_value=1, value=50)
                with col_b:
                    new_address = st.text_input("完整地址*", key="new_address", help="範例：新北市淡水區英專路15號")
                    new_region = st.text_input("區域*", key="new_region", value="淡江大學")
                    new_stock = st.number_input("初始庫存", min_value=1, value=10)
                
                new_mode = st.radio("營運模式", ['剩食', '排隊'], horizontal=True)
                
                submitted = st.form_submit_button("✅ 新增並定位")
                
                if submitted:
                    if not all([new_shop_name, new_address]):
                        st.error("店名和地址不可為空！")
                    else:
                        result = add_shop_to_backend({
                            "shop_name": new_shop_name,
                            "address": new_address,
                            "region": new_region,
                            "item": new_item,
                            "price": new_price,
                            "stock": new_stock,
                            "mode": new_mode
                        })
                        if result['result'] == 'success':
                            st.success(result['message'])
                            st.balloons()
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"新增失敗: {result['message']}")
            
            # 🚀 快速進入商家後台 (保留)
            st.divider()
            st.subheader("🚀 快速進入商家後台")
            target_shop_admin = st.selectbox("選擇要管理的店家", list(SHOPS_DB.keys()))
            if st.button("進入該店後台"):
                st.query_params["mode"] = "shop"
                st.query_params["name"] = target_shop_admin
                st.rerun()
            
            # (QR Code 功能保留)
            st.divider()
            st.subheader("📱 產生 QR Code")
            qr_shop = st.selectbox("選擇店家 (QR Code)", list(SHOPS_DB.keys()))
            shop_link = f"{BASE_APP_URL}/?mode=shop&name={urllib.parse.quote(qr_shop)}"
            st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(shop_link)}")
            st.code(shop_link)

            if st.button("清除快取"):
                st.cache_data.clear()
                st.rerun()


    # --- 主畫面 (Consumer Logic) ---
    st.title("🍱 餓不死地圖")
    st.info(f"您的唯一ID：{st.session_state['user_uuid'][:8]}... | 此ID用於防範棄單。")
    
    if not SHOPS_DB:
        st.warning("⚠️ 無法讀取店家資料，請檢查 Google Sheet 設定。")
        st.stop()

    # (其餘地圖、篩選邏輯不變)
    all_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
    selected_region = st.selectbox("📍 請選擇區域", ["所有區域"] + all_regions)
    
    if selected_region == "所有區域":
        filtered_shops = SHOPS_DB
    else:
        filtered_shops = {k: v for k: v in SHOPS_DB.items() if v['region'] == selected_region}

    # 地圖顯示
    map_df = pd.DataFrame([
        {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in filtered_shops.items()
    ])
    map_zoom = 7 if selected_region == "所有區域" else 14
    st.map(map_df, zoom=map_zoom, use_container_width=True)
    
    st.divider()

    # 3. 下單與排隊
    c1, c2 = st.columns([1.2, 1])
    
    with c1:
        st.subheader("🛒 選擇店家")
        
        target = st.selectbox("請選擇店家", list(filtered_shops.keys()))
        info = filtered_shops[target]
        is_queue_mode = info.get('mode') == '排隊' 
        
        queue_count = 0
        if not ORDERS_DF.empty:
            shop_orders = ORDERS_DF[ORDERS_DF.apply(lambda x: target in str(x.values), axis=1)]
            queue_count = len(shop_orders)
        
        current_stock = info['stock'] - queue_count
        if current_stock < 0: current_stock = 0
        
        # 顯示資訊卡片
        st.success(f"📍 **{target}** ({info['region']})")
        
        status_text = ""
        if is_queue_mode:
            status_text = f"**模式：餐期排隊**\n\n👥 目前前方有 **{queue_count}** 組候位"
        elif current_stock > 0:
            status_text = f"**模式：剩食銷售**\n\n🍱 商品：{info['item']}\n💲 價格：${info['price']}\n📦 剩餘：**{current_stock}** 份"
        else:
            status_text = f"**模式：剩食銷售**\n\n❌ **已售完**"
            
        st.markdown(status_text)
        
        gmap_url = f"https://www.google.com/maps/search/?api=1&query={info['lat']},{info['lon']}"
        st.link_button("🚗 開啟 Google Map 導航前往", gmap_url)
        
        # 🔴 暱稱輸入 (用於顯示，ID仍為UUID) 🔴
        u_name = st.text_input("輸入您的暱稱 (作為取餐/叫號依據)")
        
        if is_queue_mode:
            btn_txt = "🚪 領取號碼牌 (排隊)"
            btn_state = False
        else:
            btn_txt = "🚀 立即搶購 (剩食)"
            btn_state = (current_stock <= 0)
        
        if st.button(btn_txt, type="primary", disabled=btn_state, use_container_width=True):
            if u_name:
                with st.spinner("連線中..."):
                    try:
                        full_item = f"{target} - {info['item']}"
                        # 傳送 UUID 作為 user_id
                        requests.post(GAS_URL, json={
                            'action': 'order', 
                            'user_id': st.session_state['user_uuid'], 
                            'user': u_name,
                            'store': target,
                            'item': full_item
                        })
                        st.success(f"成功！")
                        st.balloons()
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except: st.error("連線失敗")
            else: st.warning("請輸入名字")

    with c2:
        st.subheader("📋 即時名單/排隊狀態")
        
        if not ORDERS_DF.empty:
            display_df = ORDERS_DF[ORDERS_DF.apply(lambda x: target in str(x.values), axis=1)].copy()
            
            if display_df.empty and len(ALL_ORDERS) > 0:
                st.caption("全區訂單總覽")
                st.dataframe(ORDERS_DF.tail(10))

            if not display_df.empty:
                display_df['號碼牌'] = range(1, len(display_df) + 1)
                
                if is_admin:
                    st.write("🛠️ 管理員操作")
                    del_opts = [f"{i}: {r['號碼牌']}. {r.get('user', r.get('姓名','?'))} - {r.get('item','?')}" for i, r in display_df.iterrows()]
                    target_del = st.selectbox("刪除訂單/叫號", del_opts)
                    if st.button("🗑️ 確認刪除"):
                        idx = int(target_del.split(":")[0])
                        delete_order(idx)
                        st.rerun()
                
                cols_to_show = ['號碼牌', '時間', 'user', 'item']
                st.dataframe(display_df[cols_to_show].tail(10), use_container_width=True)
            else:
                st.info("目前這家店沒人排隊")
