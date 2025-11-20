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
# 由於 GAS URL 包含敏感資訊，這裡假定它在 st.secrets 或配置中
# 為確保程式碼可運行性，使用您的原連結
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
            # 刪除 gspread 找到的 row index (從 1 開始，且標頭佔用 1)
            # 這裡的 idx 是 DataFrame 的 index (從 0 開始)，所以要加 2
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

# --- 新增：計算店家狀態的函式 ---
def get_shop_status(shop_name, shop_info, orders_df):
    """計算並返回單個店家的即時狀態和相關數據"""
    
    # 篩選該店家的訂單
    if orders_df.empty or 'store' not in orders_df.columns:
        queue_count = 0
    else:
        shop_orders = orders_df[orders_df['store'] == shop_name].copy()
        queue_count = len(shop_orders)

    is_queue_mode = shop_info.get('mode') == '排隊'
    current_stock = shop_info['stock'] - queue_count
    if current_stock < 0: current_stock = 0

    if is_queue_mode:
        status_text = f"👥 **排隊中：{queue_count}** 組"
        is_available = True
    elif current_stock > 0:
        status_text = f"📦 **剩餘：{current_stock}** 份"
        is_available = True
    else:
        status_text = "❌ **已售完 / 休息中**"
        is_available = False
        
    return {
        'queue_count': queue_count,
        'current_stock': current_stock,
        'is_available': is_available,
        'status_text': status_text,
        'is_queue_mode': is_queue_mode
    }
# --- 函式結束 ---


# ==========================================
# 3. 頁面開始
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱", layout="wide")

SHOPS_DB, ALL_ORDERS = load_data()

# 確保 ORDERS_DF 存在並包含 'user_id' 欄位
if not ALL_ORDERS:
    ORDERS_DF = pd.DataFrame()
else:
    ORDERS_DF = pd.DataFrame(ALL_ORDERS)
    if 'user_id' not in ORDERS_DF.columns:
        ORDERS_DF['user_id'] = ''
    if 'store' not in ORDERS_DF.columns:
        ORDERS_DF['store'] = ''

params = st.query_params
current_mode = params.get("mode", "consumer")
shop_target = params.get("name", None)

# --- 商家後台模式 (A) ---
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
    if not ORDERS_DF.empty and 'store' in ORDERS_DF.columns:
        shop_orders = ORDERS_DF[ORDERS_DF['store'] == shop_target].copy()
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
        # 為了後台操作，需要保留原始 Index (用來刪除)
        shop_orders_display = shop_orders.reset_index().rename(columns={'index': 'original_index'})
        shop_orders_display['號碼牌'] = range(1, len(shop_orders_display) + 1)
        
        # 管理員操作
        st.write("🛠️ 管理員操作")
        del_opts = [f"{r['original_index']}:{r['號碼牌']}. {r.get('user', '?')} - {r.get('item', '?')}" for i, r in shop_orders_display.iterrows()]
        target_del = st.selectbox("刪除訂單/叫號", del_opts)
        
        if st.button("🗑️ 確認刪除"):
            idx = int(target_del.split(":")[0])
            if delete_order(idx):
                st.success("刪除成功！")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("刪除失敗，請檢查權限或連線。")
                
        # 顯示訂單列表
        st.dataframe(shop_orders_display[['號碼牌', '時間', 'user', 'item']], use_container_width=True)
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

    # 區域篩選
    all_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
    selected_region = st.selectbox("📍 請選擇區域", ["所有區域"] + all_regions)
    
    if selected_region == "所有區域":
        filtered_shops = SHOPS_DB
    else:
        filtered_shops = {k: v for k, v in SHOPS_DB.items() if v['region'] == selected_region}
    
    # 計算地圖中心點和縮放比例 (已修正)
    map_df = pd.DataFrame([
        {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in filtered_shops.items()
    ])
    
    center_lat = 23.6 
    center_lon = 120.9
    map_zoom = 7 
    
    if not map_df.empty:
        if selected_region != "所有區域":
            center_lat = map_df['lat'].mean()
            center_lon = map_df['lon'].mean()
            map_zoom = 14 
        else:
            center_lat = map_df['lat'].mean()
            center_lon = map_df['lon'].mean()

    # 顯示地圖 (使用計算後的中心點)
    st.map(
        map_df, 
        latitude=center_lat, 
        longitude=center_lon, 
        zoom=map_zoom, 
        use_container_width=True
    )
    
    st.divider()

    # --- 顯示人潮多寡列表 (使用 Form 確保點擊跳轉穩定性) ---
    st.subheader("📊 即時人潮狀態一覽")
    
    if not filtered_shops:
        st.info("所選區域目前沒有任何店家資訊。")
    else:
        # 1. 計算店家狀態 (保持不變)
        shops_with_status = []
        for name, info in filtered_shops.items():
            status = get_shop_status(name, info, ORDERS_DF)
            shops_with_status.append({'name': name, 'info': info, 'status': status})
        
        # 2. 排序邏輯 (保持不變)
        shops_with_status.sort(key=lambda x: (
            not x['status']['is_available'], 
            x['status']['is_queue_mode'],    
            -x['status']['current_stock'] if not x['status']['is_queue_mode'] else x['status']['queue_count'] 
        ))
        
        cols_per_row = 3
        cols = st.columns(cols_per_row)
        
        # --- 使用一個隱藏的 Form 來包裝所有按鈕，確保點擊後的狀態更新 ---
        with st.form("shop_list_form"):
            
            # 遍歷店家並在 Columns 中顯示
            for i, shop in enumerate(shops_with_status):
                name = shop['name']
                info = shop['info']
                status = shop['status']
                
                with cols[i % cols_per_row]:
                    
                    # 判斷使用者的下單狀態
                    user_is_in_queue = False
                    my_queue_number = 0
                    if not ORDERS_DF.empty and 'user_id' in ORDERS_DF.columns and 'store' in ORDERS_DF.columns:
                        my_queue = ORDERS_DF[(ORDERS_DF['user_id'] == st.session_state['user_uuid']) & (ORDERS_DF['store'] == name)]
                        if not my_queue.empty:
                            user_is_in_queue = True
                            # 計算隊伍號碼
                            shop_orders = ORDERS_DF[ORDERS_DF['store'] == name]
                            my_order_index = my_queue.index[0]
                            # 找出自己在篩選後的 dataframe 中的位置
                            my_queue_number = len(shop_orders[shop_orders.index <= my_order_index])


                    # 創建簡潔卡片
                    with st.container(border=True):
                        st.markdown(f"**🏪 {name}** ({info['region']})")
                        
                        # 顯示人潮狀態
                        st.markdown(f"**{status['status_text']}**")
                        
                        if status['is_queue_mode']:
                            st.caption(f"模式：餐期排隊 | 叫號依據：**{info['item']}**")
                        elif status['is_available']:
                            st.caption(f"模式：剩食 | 價格：**${info['price']}**")

                        # 顯示用戶自己的狀態
                        if user_is_in_queue:
                            st.success(f"🎉 **您排在 {my_queue_number} 號！**")
                            
                        # --- 關鍵修正：使用 st.form_submit_button 觸發跳轉 ---
                        if status['is_available'] and not user_is_in_queue:
                            st.form_submit_button(
                                "我要排隊/搶購", 
                                type="primary", 
                                help="點擊進入詳細下單頁面",
                                use_container_width=True,
                                # 使用 key 傳遞店家名稱，這個 key 會在 session_state 中被設置
                                key=f"submit_btn_{name}" 
                            )
                        elif user_is_in_queue:
                            st.button("已在隊伍中", key=f"disabled_btn_{name}", disabled=True, use_container_width=True)
                        else:
                            st.button("休息中", key=f"unavailable_btn_{name}", disabled=True, use_container_width=True)
            
            # Form 提交按鈕是必須的，但我們讓它隱藏
            # 由於我們使用 Form Submit Button 的 Key 特性，這個 submit button 實際上不需要
            # 但如果 Streamlit 要求至少有一個 submit button，可以保留一個隱藏的，這裡選擇不保留。


        # --- 處理 Form 提交後的跳轉 (在 Form 外執行) ---
        submitted = False
        target_shop_to_jump = None
        
        # 遍歷檢查是哪個 form_submit_button 被點擊了
        for shop in shops_with_status:
            name = shop['name']
            if st.session_state.get(f"submit_btn_{name}"):
                target_shop_to_jump = name
                # 必須重設 session_state，否則會無限循環 Rerun
                st.session_state[f"submit_btn_{name}"] = False 
                submitted = True
                break
        
        if submitted and target_shop_to_jump:
            st.query_params['target_shop'] = target_shop_to_jump
            st.rerun() 
            
        # --- 處理從列表跳轉到詳細頁面 ---
        
        st.divider()
        
        # 檢查是否從上面的列表點擊了「我要排隊/搶購」
        if 'target_shop' in st.query_params and st.query_params['target_shop'] in filtered_shops:
            target_shop_name = st.query_params['target_shop']
            
            st.subheader(f"🛒 立即排隊/搶購 - {target_shop_name}")
            info = filtered_shops[target_shop_name]
            status = get_shop_status(target_shop_name, info, ORDERS_DF)
            
            # 顯示詳細資訊和下單表單 
            if status['is_available']:
                st.markdown(f"**狀態：** {status['status_text']}")
                
                u_name = st.text_input("輸入您的暱稱 (作為取餐/叫號依據)", key="u_name_detail")
                
                btn_txt = "🚪 領取號碼牌 (排隊)" if status['is_queue_mode'] else "🚀 立即搶購 (剩食)"
                
                if st.button(btn_txt, type="primary", use_container_width=True, key="detail_order_btn"):
                    # 執行下單邏輯 
                    if u_name:
                        user_has_order = False
                        if not ORDERS_DF.empty:
                            user_has_order = not ORDERS_DF[(ORDERS_DF['user_id'] == st.session_state['user_uuid']) & (ORDERS_DF['store'] == target_shop_name)].empty
                        
                        if user_has_order:
                            st.warning("⚠️ 您已經下過單（或正在排隊）了，請勿重複操作。")
                        else:
                            with st.spinner("連線中..."):
                                try:
                                    full_item = f"{target_shop_name} - {info['item']}"
                                    requests.post(GAS_URL, json={
                                        'action': 'order', 
                                        'user_id': st.session_state['user_uuid'], 
                                        'user': u_name,
                                        'store': target_shop_name,
                                        'item': full_item
                                    })
                                    st.success(f"成功！")
                                    st.balloons()
                                    st.cache_data.clear()
                                    # 移除 target_shop 參數，回到列表
                                    st.query_params.pop('target_shop')
                                    st.rerun()
                                except: 
                                    st.error("連線失敗")
                    else: st.warning("請輸入名字")

                st.link_button("🔙 返回人潮狀態列表", f"{BASE_APP_URL}/?mode=consumer")
            else:
                st.warning(f"{target_shop_name} 目前已售完或休息中。")
                st.link_button("🔙 返回人潮狀態列表", f"{BASE_APP_URL}/?mode=consumer")
