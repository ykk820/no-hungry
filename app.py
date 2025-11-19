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
GAS_URL = "https://script.google.com/macros/s/AKfycbwZsrOvS7QrNTaXVcJo1L7HZpmcUSvjZg6JPOPjPbW5-9EYzRUzVYxVs0K--Tp93DxhKQ/exec"
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"
BASE_APP_URL = "https://no-hungry.streamlit.app" 

# ==========================================
# 2. 資料庫連線函式
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
    """讀取店家設定(含地區/模式) & 領取紀錄"""
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
                        'mode': str(row.get('模式', '剩食')).strip(), # 🔴 新增：模式 🔴
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

# ==========================================
# 🏪 模式 A: 商家後台 (動態適應 剩食/排隊)
# ==========================================
if current_mode == "shop" and shop_target in SHOPS_DB:
    
    shop_info = SHOPS_DB[shop_target]
    is_queue_mode = shop_info.get('mode') == '排隊'
    
    st.title(f"🏪 {shop_target} - 商家後台")
    st.caption(f"目前模式: {'**排隊叫號**' if is_queue_mode else '**剩食銷售**'}")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()
        
    # 計算數據
    shop_orders = pd.DataFrame()
    sold_or_queued = 0
    if not ORDERS_DF.empty:
        shop_orders = ORDERS_DF[ORDERS_DF.apply(lambda x: shop_target in str(x.values), axis=1)]
        sold_or_queued = len(shop_orders)
    
    # 根據模式顯示不同的儀表板
    col1, col2, col3 = st.columns(3)
    
    if is_queue_mode:
        # 排隊模式只顯示排隊人數
        col1.metric("👥 總叫號人數", sold_or_queued)
        col2.metric("📋 目前隊伍長度", sold_or_queued)
        col3.metric("💡 模式", "排隊叫號中")
    else:
        # 剩食模式顯示庫存和營收
        remain = shop_info['stock'] - sold_or_queued
        rev = sold_or_queued * shop_info['price']
        col1.metric("📦 總庫存", shop_info['stock'])
        col2.metric("✅ 已售出", sold_or_queued)
        col3.metric("🔥 剩餘", remain, delta_color="inverse")
        st.metric("💰 預估營收", f"${rev}") # 獨立一行
    
    st.divider()
    st.subheader("📋 待處理名單")
    
    if not shop_orders.empty:
        cols = [c for c in shop_orders.columns if c in ['時間', '姓名', 'user', 'item']]
        
        # 顯示排隊號碼 (Queue Number)
        shop_orders['號碼牌'] = range(1, len(shop_orders) + 1)
        
        display_cols = ['號碼牌'] + cols
        
        st.dataframe(shop_orders[display_cols], use_container_width=True)
    else:
        st.info("目前無待處理訂單或排隊者")
        
    if st.button("⬅️ 回首頁"):
        st.query_params.clear()
        st.rerun()

# ==========================================
# 🗺️ 模式 B: 消費者 + 管理員 (主頁)
# ==========================================
else:
    # --- 側邊欄：管理員 ---
    with st.sidebar:
        st.header("🔒 管理員")
        pwd = st.text_input("密碼", type="password")
        is_admin = (pwd == "ykk8880820")
        
        if is_admin:
            st.success("已登入")
            st.divider()
            
            st.subheader("🚀 快速進入商家後台")
            target_shop_admin = st.selectbox("選擇要管理的店家", list(SHOPS_DB.keys()))
            if st.button("進入該店後台"):
                st.query_params["mode"] = "shop"
                st.query_params["name"] = target_shop_admin
                st.rerun()
            
            st.divider()
            if st.button("🗑️ 清除快取"):
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
    
    if selected_region == "所有區域":
        filtered_shops = SHOPS_DB
    else:
        filtered_shops = {k: v for k, v in SHOPS_DB.items() if v['region'] == selected_region}

    # 2. 地圖顯示
    if filtered_shops:
        map_df = pd.DataFrame([
            {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in filtered_shops.items()
        ])
        map_zoom = 7 if selected_region == "所有區域" else 14
        st.map(map_df, zoom=map_zoom, use_container_width=True)
    else:
        st.info("該區域目前沒有合作店家。")

    st.divider()

    # 3. 下單與列表
    c1, c2 = st.columns([1.2, 1])
    
    with c1:
        st.subheader("🛒 選擇店家")
        
        target = st.selectbox("請選擇店家", list(filtered_shops.keys()))
        info = filtered_shops[target]
        is_queue_mode = info.get('mode') == '排隊' # 🔴 模式判斷 🔴
        
        # 計算排隊人數與庫存
        queue_count = 0
        if not ORDERS_DF.empty:
            shop_orders = ORDERS_DF[ORDERS_DF.apply(lambda x: target in str(x.values), axis=1)]
            queue_count = len(shop_orders)
        
        current_stock = info['stock'] - queue_count
        if current_stock < 0: current_stock = 0
        
        # 顯示資訊卡片 (根據模式調整)
        st.success(f"📍 **{target}** ({info['region']})")
        
        status_text = ""
        if is_queue_mode:
            status_text = f"**模式：餐期叫號**\n\n👥 目前前方有 **{queue_count}** 組排隊"
        elif current_stock > 0:
            status_text = f"**模式：剩食銷售**\n\n🍱 商品：{info['item']}\n💲 價格：${info['price']}\n📦 剩餘：**{current_stock}** 份"
        else:
            status_text = f"**模式：剩食銷售**\n\n❌ **已售完**"
            
        st.markdown(status_text)
        
        # 導航按鈕
        gmap_url = f"https://www.google.com/maps/search/?api=1&query={info['lat']},{info['lon']}"
        st.link_button("🚗 開啟 Google Map 導航前往", gmap_url)
        
        u_name = st.text_input("輸入您的暱稱 (作為取餐/叫號依據)")
        
        # 按鈕文案與狀態 (根據模式調整)
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
                        response = requests.post(GAS_URL, json={'user': u_name, 'item': full_item})
                        
                        if response.status_code == 200:
                            res = response.json()
                            if res.get("result") == "success":
                                st.balloons()
                                if is_queue_mode:
                                    st.success(f"領號成功！您是目前第 {queue_count + 1} 組。")
                                else:
                                    st.success(f"搶購成功！{res.get('message')}")
                                
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"{res.get('message')}") # 顯示限購錯誤
                        else:
                            st.error("連線失敗，請重試。")
                    except Exception as e:
                        st.error(f"發生錯誤: {e}")
            else:
                st.warning("請輸入名字")

    with c2:
        st.subheader("📋 即時名單/排隊狀況")
        
        if not ORDERS_DF.empty:
            # 顯示目前選定店家的狀況
            display_df = ORDERS_DF[ORDERS_DF.apply(lambda x: target in str(x.values), axis=1)].copy()
            st.caption(f"顯示 {target} 的排隊/搶購狀況")

            if not display_df.empty:
                # 🔴 加上號碼牌 🔴
                display_df['號碼牌'] = range(1, len(display_df) + 1)
                
                # 管理員刪單功能
                if is_admin:
                    st.write("🛠️ 管理員操作")
                    del_opts = [f"{i}: {r['號碼牌']}. {r.get('user', r.get('姓名','?'))} - {r.get('item','?')}" for i, r in display_df.iterrows()]
                    target_del = st.selectbox("刪除訂單/叫號", del_opts)
                    if st.button("🗑️ 確認刪除"):
                        idx = int(target_del.split(":")[0])
                        delete_order(idx)
                        st.rerun()
                
                # 顯示表格
                cols_to_show = ['號碼牌', '時間', 'user', 'item']
                st.dataframe(display_df[cols_to_show].tail(10), use_container_width=True)
            else:
                st.info("目前這家店沒人排隊或搶購")
        else:
            st.info("尚無任何訂單")
