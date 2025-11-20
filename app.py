import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse
import time
import uuid 
# --- 新增 geopy 函式庫 ---
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError 
from datetime import datetime # 用於訂單寫入

# ==========================================
# 0. 設置唯一身份識別碼 (UUID)
# ==========================================
if 'user_uuid' not in st.session_state:
    st.session_state['user_uuid'] = str(uuid.uuid4())

# ==========================================
# 1. 系統全域設定 
# ==========================================
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"
BASE_APP_URL = "https://no-hungry.streamlit.app"

# --- 新增：淡江大學周邊的建議/標準化區域名稱 ---
SUGGESTED_REGIONS = [
    '淡江大學',
    '金雞母/水源街',
    '大田寮',
    '英專路/老街',
    '淡海新市鎮',
    '紅樹林/竹圍'
]

# ==========================================
# 2. 資料庫連線函式與服務 
# ==========================================

# --- 地區名稱清理函式 ---
def clean_region_name(name):
    """移除前後空白並替換常見的特殊空白符號，用於保證篩選比對成功"""
    if isinstance(name, str):
        return name.strip().replace('\u3000', '').strip()
    return str(name).strip()


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
                    cleaned_region = clean_region_name(row.get('地區', '未分類'))
                    
                    shops_db[name] = {
                        'region': cleaned_region, 
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

# --- FIX: Nominatim Geocoding 服務函式 (無需 Key) ---
@st.cache_data(ttl=3600) # 緩存定位結果一小時
def geocode_with_nominatim(address):
    """使用 OpenStreetMap Nominatim 服務將地址轉換為經緯度"""
    try:
        geolocator = Nominatim(user_agent="No_Hungry_App_Taiwan")
        location = geolocator.geocode(address, timeout=10) 
        
        if location:
            return location.latitude, location.longitude, "定位成功"
        else:
            return None, None, "錯誤：找不到地址的定位結果"
            
    except GeocoderTimedOut:
        return None, None, "錯誤：定位服務超時，請重試"
    except GeocoderServiceError as e:
        return None, None, f"錯誤：定位服務無法連線 ({e})"
    except Exception as e:
        return None, None, f"定位 API 呼叫失敗: {str(e)}"


# --- FIX: 重構 add_shop_to_sheet (直接在 Streamlit 內處理定位與寫入) ---
def add_shop_to_sheet(data):
    
    # 1. 執行 Geocoding
    st.info(f"正在使用 OpenStreetMap 服務定位地址: {data['address']}...")
    # FIX: 呼叫 Nominatim 定位函式
    lat, lon, message = geocode_with_nominatim(data['address'])
    
    if lat is None:
        st.error(f"店家新增失敗。定位錯誤訊息: {message}")
        return False
        
    client = get_client()
    if not client:
        st.error("店家新增失敗。無法連線至 Google Sheets (請檢查 GCP 服務帳戶金鑰)")
        return False

    # 2. 準備寫入資料 (順序必須與 Google Sheet 欄位一致)
    new_row = [
        data['shop_name'], 
        data['region'], 
        data['mode'], 
        lat, # 定位後的緯度
        lon, # 定位後的經度
        data['item'], 
        data['price'], 
        data['stock']
    ]

    # 3. 執行寫入
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet("店家設定")
        ws.append_row(new_row, value_input_option='USER_ENTERED')
        
        st.success(f"✅ 店家 **{data['shop_name']}** 新增成功！(經緯度: {lat}, {lon})")
        st.balloons()
        st.cache_data.clear() # 清除快取，讓新資料立即顯示
        st.rerun()
    except Exception as e:
        st.error(f"寫入 Google Sheet 失敗: {str(e)}。請檢查工作表名稱或權限。")
        return False

def get_shop_status(shop_name, shop_info, orders_df):
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


# ==========================================
# 3. 頁面開始
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱", layout="wide")

SHOPS_DB, ALL_ORDERS = load_data()

if not ALL_ORDERS:
    ORDERS_DF = pd.DataFrame()
else:
    ORDERS_DF = pd.DataFrame(ALL_ORDERS)
    if 'user_id' not in ORDERS_DF.columns: ORDERS_DF['user_id'] = ''
    if 'store' not in ORDERS_DF.columns: ORDERS_DF['store'] = ''

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
            
        st.divider()
        st.link_button("📄 開啟 Google Sheet", f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit", help="直接編輯數據庫")
        st.divider()

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
        shop_orders_display = shop_orders.reset_index().rename(columns={'index': 'original_index'})
        shop_orders_display['號碼牌'] = range(1, len(shop_orders_display) + 1)
        
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
                
        st.dataframe(shop_orders_display[['號碼牌', '時間', 'user', 'item']], use_container_width=True)
    else:
        st.info("目前無待處理訂單")


# --- 消費者 + 管理員模式 (B) ---
else:
    # --- 側邊欄：管理員 (新增店家表單 - 使用下拉選單) ---
    with st.sidebar:
        st.header("🔒 管理員")
        password = st.text_input("密碼", type="password")
        is_admin = (password == "ykk8880820")
        
        if is_admin:
            st.success("已登入")
            st.link_button("📄 開啟 Google Sheet", f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit", help="直接編輯數據庫")
            st.divider()
        
        # 獲取所有地區和模式選項
        all_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
        
        # --- 管理員新增店家表單邏輯 ---
        if is_admin:
            # 整合建議區域到管理員新增介面
            region_options_base = sorted(list(set(SUGGESTED_REGIONS + all_regions)))
            new_region_options = ["新增區域..."] + region_options_base
            
            st.subheader("➕ 一鍵新增店家 (標準化區域)")
            st.caption("**使用 OpenStreetMap 進行定位 (無需 Key)**")
            st.caption("建議選擇清單中的標準化區域名稱")
            with st.form("add_shop_form"):
                col_a, col_b = st.columns(2)
                with col_a:
                    new_shop_name = st.text_input("店名*", key="new_shop_name")
                    new_item = st.text_input("商品名*", key="new_item", value="剩食套餐")
                    new_price = st.number_input("價格*", min_value=1, value=50)
                with col_b:
                    new_address = st.text_input("完整地址*", key="new_address", help="範例：新北市淡水區英專路15號 (將用於自動定位)")
                    
                    selected_region_input = st.selectbox(
                        "選擇或輸入區域*", 
                        new_region_options, 
                        index=new_region_options.index("新增區域...") if "新增區域..." in new_region_options else 0
                    )
                    
                    if selected_region_input == "新增區域...":
                        new_region = st.text_input("輸入新區域名稱", key="new_region_manual", value="淡江大學")
                    else:
                        new_region = selected_region_input
                        
                    new_stock = st.number_input("初始庫存", min_value=1, value=10)
                
                new_mode_options = ['剩食', '排隊']
                new_mode = st.selectbox("營運模式", new_mode_options, index=new_mode_options.index('剩食'))
                
                submitted = st.form_submit_button("✅ 新增並定位 (直接寫入 Sheet)")
                
                # --- FIX: 直接呼叫 Streamlit 內建的寫入邏輯 ---
                if submitted:
                    cleaned_region_name = clean_region_name(new_region)
                    if not all([new_shop_name, new_address, cleaned_region_name]):
                        st.error("店名、地址和區域不可為空！")
                    else:
                        # 執行定位和寫入
                        add_shop_to_sheet({
                            "shop_name": new_shop_name,
                            "address": new_address,
                            "region": cleaned_region_name, 
                            "item": new_item,
                            "price": new_price,
                            "stock": new_stock,
                            "mode": new_mode
                        })
            
            # 🚀 快速進入商家後台 
            st.divider()
            st.subheader("🚀 快速進入商家後台")
            target_shop_admin = st.selectbox("選擇要管理的店家", list(SHOPS_DB.keys()))
            if st.button("進入該店後台"):
                st.query_params["mode"] = "shop"
                st.query_params["name"] = target_shop_admin
                st.rerun()
                
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

    # --- 篩選器與狀態管理 ---
    all_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
    default_region_index = 0
    
    if "淡江大學" in all_regions:
         default_region_index = all_regions.index("淡江大學") + 1 

    if 'selected_region' not in st.session_state:
        st.session_state['selected_region'] = "所有區域"
    if 'target_shop_select' not in st.session_state:
        st.session_state['target_shop_select'] = None
    
    # --- 篩選器 ---
    col_filter_1, col_filter_2 = st.columns([1, 4])

    with col_filter_1:
        selected_region = st.selectbox(
            "📍 請選擇區域", 
            ["所有區域"] + all_regions,
            index=default_region_index,
            key="region_selectbox",
            on_change=lambda: st.session_state.update(
                selected_region=st.session_state.region_selectbox,
                target_shop_select=None 
            )
        )
        
        # --- 數據驗證區塊 (Sheet 連結 Map) ---
        with st.expander("🔬 檢查地圖數據"):
             st.caption("顯示地圖上正在使用的店家資料")
             show_data_map = st.checkbox("顯示原始地圖數據", value=False)


    cleaned_selected_region = clean_region_name(st.session_state['selected_region'])

    if cleaned_selected_region == "所有區域":
        filtered_shops = SHOPS_DB
    else:
        filtered_shops = {k: v for k, v in SHOPS_DB.items() if v['region'] == cleaned_selected_region}
    
    if not filtered_shops and cleaned_selected_region != "所有區域":
        st.warning(f"🚨 警告：選定區域 **{st.session_state['selected_region']}** 下找不到店家。請檢查 Google Sheet 中的地區名稱是否完全一致。")
    
    # --- 地圖顯示 ---
    
    map_df = pd.DataFrame([
        {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in filtered_shops.items()
    ])
    
    center_lat = 23.6 
    center_lon = 120.9
    map_zoom = 7 
    
    if not map_df.empty:
        if cleaned_selected_region != "所有區域":
            center_lat = map_df['lat'].mean()
            center_lon = map_df['lon'].mean()
            map_zoom = 14 
        else:
            center_lat = map_df['lat'].mean()
            center_lon = map_df['lon'].mean()

    with col_filter_2:
        st.map(
            map_df, 
            latitude=center_lat, 
            longitude=center_lon, 
            zoom=map_zoom, 
            use_container_width=True
        )
        # --- 在地圖旁顯示數據驗證表 ---
        if show_data_map and not map_df.empty:
            st.dataframe(map_df, use_container_width=True, height=200)

    st.divider()

    # --- 顯示人潮多寡列表與連動選擇 ---
    
    st.subheader("📊 即時人潮狀態一覽 (點擊卡片選擇店家)")
    
    shops_with_status = []
    for name, info in filtered_shops.items():
        status = get_shop_status(name, info, ORDERS_DF)
        shops_with_status.append({'name': name, 'info': info, 'status': status})
    
    shops_with_status.sort(key=lambda x: (
        not x['status']['is_available'], 
        x['status']['is_queue_mode'],    
        -x['status']['current_stock'] if not x['status']['is_queue_mode'] else x['status']['queue_count'] 
    ))
    
    # 顯示列表
    cols_per_row = 3
    if len(shops_with_status) == 0:
        st.info(f"在 **{st.session_state['selected_region']}** 區域內沒有找到任何店家。")
    else:
        cols = st.columns(cols_per_row)
        
        # --- 使用 Form 確保點擊連動穩定性 (FINAL STRUCTURE) ---
        with st.form("shop_list_form"):
            
            for i, shop in enumerate(shops_with_status):
                name = shop['name']
                info = shop['info']
                status = shop['status']
                
                user_is_in_queue = False
                my_queue_number = 0
                if not ORDERS_DF.empty and 'user_id' in ORDERS_DF.columns and 'store' in ORDERS_DF.columns:
                    my_queue = ORDERS_DF[(ORDERS_DF['user_id'] == st.session_state['user_uuid']) & (ORDERS_DF['store'] == name)]
                    if not my_queue.empty:
                        user_is_in_queue = True
                        shop_orders = ORDERS_DF[ORDERS_DF['store'] == name]
                        my_order_index = my_queue.index[0]
                        my_queue_number = len(shop_orders[shop_orders.index <= my_order_index])


                with cols[i % cols_per_row]:
                    
                    border_color = True
                    if st.session_state['target_shop_select'] == name:
                        border_color = "green" 

                    # 1. 顯示卡片內容
                    with st.container(border=border_color): 
                        st.markdown(f"**🏪 {name}** ({info['region']})")
                        st.markdown(f"**{status['status_text']}**")
                        
                        if status['is_queue_mode']:
                            st.caption(f"模式：餐期排隊 | 叫號依據：**{info['item']}**")
                        elif status['is_available']:
                            st.caption(f"模式：剩食 | 價格：**${info['price']}**")

                        if user_is_in_queue:
                            st.success(f"🎉 **您排在 {my_queue_number} 號！**")
                            
                    # 2. 顯示按鈕 (位於 with cols 內，但與 container 平行)
                    if status['is_available']:
                        if st.form_submit_button(
                            f"選擇 {name} 進行下單", 
                            type="primary" if st.session_state['target_shop_select'] != name else "secondary",
                            use_container_width=True,
                            key=f"select_btn_{name}" 
                        ):
                            st.session_state['target_shop_select'] = name
                            
                    else:
                        st.button("休息中 / 已售完", key=f"unavailable_btn_{name}", disabled=True, use_container_width=True)
            
        shop_selected_by_click = False
        for shop in shops_with_status:
            name = shop['name']
            if st.session_state.get(f"select_btn_{name}"):
                st.session_state[f"select_btn_{name}"] = False 
                shop_selected_by_click = True
                break
                
        if shop_selected_by_click:
            st.rerun()

    # --- 4. 詳細下單/排隊區塊 ---
    
    st.divider()
    
    if st.session_state['target_shop_select'] and st.session_state['target_shop_select'] in filtered_shops:
        target_shop_name = st.session_state['target_shop_select']
        
        st.subheader(f"🛒 立即排隊/搶購 - {target_shop_name}")
        info = filtered_shops[target_shop_name]
        status = get_shop_status(target_shop_name, info, ORDERS_DF)
        
        if status['is_available']:
            st.success(f"狀態：{status['status_text']}")
            
            u_name = st.text_input("輸入您的暱稱 (作為取餐/叫號依據)", key="u_name_detail")
            
            btn_txt = "🚪 領取號碼牌 (排隊)" if status['is_queue_mode'] else "🚀 立即搶購 (剩食)"
            
            user_has_order = False
            if not ORDERS_DF.empty:
                user_has_order = not ORDERS_DF[(ORDERS_DF['user_id'] == st.session_state['user_uuid']) & (ORDERS_DF['store'] == target_shop_name)].empty
            
            if user_has_order:
                st.warning("⚠️ 您已經下過單（或正在排隊）了，請勿重複操作。")
                st.button(f"{btn_txt} (已完成)", disabled=True, use_container_width=True)
            elif st.button(btn_txt, type="primary", use_container_width=True, key="detail_order_btn"):
                if u_name:
                    with st.spinner("連線中..."):
                        try:
                            full_item = f"{target_shop_name} - {info['item']}"
                            
                            # --- 訂單寫入邏輯 ---
                            client = get_client()
                            if client:
                                ws_orders = client.open_by_key(SPREADSHEET_ID).worksheet("領取紀錄")
                                new_order_row = [
                                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                                    st.session_state['user_uuid'], 
                                    u_name, 
                                    target_shop_name, 
                                    full_item
                                ]
                                ws_orders.append_row(new_order_row, value_input_option='USER_ENTERED')
                                
                                st.success(f"下單成功！請前往 {target_shop_name} 取餐。")
                                st.balloons()
                                st.cache_data.clear()
                                st.session_state['target_shop_select'] = None 
                                st.rerun()
                            else:
                                st.error("無法連線至 Google Sheet 處理訂單，請檢查權限設定。")

                        except Exception as e: 
                            st.error(f"訂單處理失敗: {e}")
                else: st.warning("請輸入名字")

        else:
            st.warning(f"{target_shop_name} 目前已售完或休息中。")
            
    elif st.session_state['target_shop_select'] and st.session_state['target_shop_select'] not in filtered_shops:
        st.warning("您選擇的店家不在當前區域篩選結果中，請重新選擇。")
        st.session_state['target_shop_select'] = None
    
    else:
        st.info("⬆️ 請在上方地圖下方點擊卡片選擇店家，進行下單或排隊。")
