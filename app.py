import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse
from datetime import datetime
import uuid 
import numpy as np 

# ==========================================
# 0. 設置唯一身份識別碼 (UUID)
# ==========================================
if 'user_uuid' not in st.session_state:
    st.session_state['user_uuid'] = str(uuid.uuid4())

# --- Session State 初始化 ---
if 'admin_login_visible' not in st.session_state:
    st.session_state['admin_login_visible'] = False
if 'target_shop_select' not in st.session_state:
     st.session_state['target_shop_select'] = None


# ==========================================
# 1. 系統全域設定 
# ==========================================
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"
BASE_APP_URL = "https://no-hungry.streamlit.app"

# --- 區域標準化名稱 (格式：[行政區] - [社區名]) ---
SUGGESTED_REGIONS_FULL = [
    '新北市淡水區 - 淡江大學',
    '新北市淡水區 - 金雞母/水源街',
    '新北市淡水區 - 大田寮',
    '新北市淡水區 - 英專路/老街',
    '新北市淡水區 - 淡海新市鎮',
    '新北市淡水區 - 紅樹林/竹圍',
]
# --- 淡江區域篩選關鍵字 (固定為此區域) ---
TAMKANG_PREFIX = '新北市淡水區'

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
                        'mode': '剩食', # 强制设为剩食模式
                        'item': str(row.get('商品', '優惠商品')),
                        'price': int(row.get('價格', 0) or 0),
                        'stock': int(row.get('初始庫存', 0) or 0)
                    }
        except Exception: shops_db = {}

        # 2. 讀取訂單
        try:
            ws_orders = ss.worksheet("領取紀錄")
            orders = ws_orders.get_all_records()
        except Exception: orders = []

        return shops_db, orders
    except Exception: 
        st.error("數據庫載入失敗，請檢查權限或 ID 是否正確。")
        return {}, []

def delete_order(idx):
    client = get_client()
    if client:
        try:
            client.open_by_key(SPREADSHEET_ID).worksheet("領取紀錄").delete_rows(idx + 2)
            return True
        except Exception: 
            st.error("操作失敗，無法刪除訂單。")
            return False
    return False

# --- 簡化後的店家新增函式 (移除 Lat/Lon 參數) ---
def add_shop_to_sheet(data):
    
    client = get_client()
    if not client:
        st.error("店家新增失敗。無法連線至數據庫。")
        return False

    # 準備寫入資料 (Lat/Lon 欄位填 0)
    new_row = [
        data['shop_name'], 
        data['region'], # 結構：行政區 - 社區名
        data['mode'], 
        0, # 緯度 (佔位)
        0, # 經度 (佔位)
        data['item'], 
        data['price'], 
        data['stock']
    ]

    # 執行寫入
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet("店家設定")
        ws.append_row(new_row, value_input_option='USER_ENTERED')
        
        st.success(f"✅ 店家 **{data['shop_name']}** 新增成功！")
        st.balloons()
        st.cache_data.clear() # 清除快取，讓新資料立即顯示
        st.rerun()
    except Exception:
        st.error("新增失敗，請檢查數據庫工作表名稱或權限。")
        return False

def get_shop_status(shop_name, shop_info, orders_df):
    if orders_df.empty or 'store' not in orders_df.columns:
        queue_count = 0
    else:
        if 'store' in ORDERS_DF.columns:
            shop_orders = ORDERS_DF[ORDERS_DF['store'] == shop_name].copy()
            queue_count = len(shop_orders)
        else:
             queue_count = 0


    is_queue_mode = False # ⚠️ 永遠設為 False (剩食模式)
    current_stock = shop_info['stock'] - queue_count
    if current_stock < 0: current_stock = 0

    if current_stock > 0:
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
        'is_queue_mode': False
    }


# ==========================================
# 3. 頁面開始
# ==========================================
st.set_page_config(page_title="餓不死清單", page_icon="🍱", layout="wide") # 更改頁面標題

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
    is_queue_mode = False
    
    with st.sidebar:
        st.title(f"🏪 {shop_target}")
        if st.button("⬅️ 登出 (回首頁)"):
            st.query_params.clear() 
            st.rerun() 
            
        st.divider()
        st.link_button("📄 開啟數據庫", f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit", help="直接編輯 Google Sheet 數據庫")
        st.divider()

    st.title(f"📊 實時剩食看板 - {shop_target}")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

    shop_orders = pd.DataFrame()
    sold_or_queued = 0
    if not ORDERS_DF.empty and 'store' in ORDERS_DF.columns:
        shop_orders = ORDERS_DF[ORDERS_DF['store'] == shop_target].copy()
        sold_or_queued = len(shop_orders)
    
    c1, c2, c3 = st.columns(3)
    remain = shop_info['stock'] - sold_or_queued
    rev = sold_or_queued * shop_info['price']
    c1.metric("📦 總庫存", shop_info['stock'])
    c2.metric("✅ 已領取", sold_or_queued)
    c3.metric("🔥 剩餘", remain, delta_color="inverse")
    
    st.divider()
    st.subheader("📋 待處理領取名單")
    
    if not shop_orders.empty:
        shop_orders_display = shop_orders.reset_index().rename(columns={'index': 'original_index'})
        shop_orders_display['號碼牌'] = range(1, len(shop_orders_display) + 1)
        
        st.write("🛠️ 管理員操作")
        del_opts = [f"{r['original_index']}:{r['號碼牌']}. {r.get('user', '?')} - {r.get('item', '?')}" for i, r in shop_orders_display.iterrows()]
        target_del = st.selectbox("完成領取/刪除訂單", del_opts)
        
        if st.button("🗑️ 確認刪除"):
            idx = int(target_del.split(":")[0])
            if delete_order(idx):
                st.success("訂單已完成領取並移除！")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("操作失敗，請檢查連線。")
                
        st.dataframe(shop_orders_display[['號碼牌', '時間', 'user', 'item']], use_container_width=True)
    else:
        st.info("目前無待處理訂單")


# --- 消費者 + 管理員模式 (B) ---
else:
    # --- 側邊欄：管理員 (控制面板) ---
    with st.sidebar:
        
        # 💡 隱藏後台介面：使用按鈕控制登入區塊的顯示
        if st.button("🔒 管理員登入", use_container_width=True):
            st.session_state['admin_login_visible'] = not st.session_state['admin_login_visible']

        if st.session_state['admin_login_visible']:
            st.divider()
            st.header("🔑 登入")
            password = st.text_input("密碼", type="password")
            is_admin = (password == "ykk8880820")
        else:
            is_admin = False

        if is_admin:
            st.success("已登入")
            st.link_button("📄 開啟數據庫", f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit", help="直接編輯 Google Sheet 數據庫")
            st.divider()
        
        # 獲取所有地區和模式選項
        all_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
        
        # --- 管理員新增店家表單邏輯 (只有登入後才顯示) ---
        if is_admin:
            # 從 SUGGESTED_REGIONS_FULL 提取行政區和社區名
            unique_main_regions = sorted(list(set([r.split(' - ')[0].strip() for r in SUGGESTED_REGIONS_FULL])))
            
            st.subheader("➕ 新增店家")
            st.caption("經緯度將設為 0, 0。")
            with st.form("add_shop_form"):
                col_a, col_b = st.columns(2)
                with col_a:
                    new_shop_name = st.text_input("店名*", key="new_shop_name")
                    new_item = st.text_input("商品名*", key="new_item", value="剩食套餐")
                    new_price = st.number_input("價格*", min_value=1, value=50) # 價格輸入
                with col_b:
                    
                    # --- 雙層地區選擇輸入 (強制行政區為 TAMKANG_PREFIX) ---
                    st.caption(f"地區：{TAMKANG_PREFIX}") # 顯示固定的行政區
                    main_region = TAMKANG_PREFIX # 固定行政區
                    
                    # 過濾出所有淡水區的社區名
                    tamkang_sub_regions = [r.split(' - ')[1].strip() for r in SUGGESTED_REGIONS_FULL if r.startswith(TAMKANG_PREFIX)]

                    sub_region = st.selectbox(
                        "選擇社區/次分區*", 
                        tamkang_sub_regions,
                        key="new_sub_region_manual"
                    )

                    # 將兩級地區合併為單一字串
                    new_region = f"{main_region} - {sub_region}" 
                    # ---------------------------

                    new_stock = st.number_input("初始庫存", min_value=1, value=10)
                
                new_mode = '剩食' # 固定為剩食模式
                
                submitted = st.form_submit_button("✅ 新增店家 (直接寫入數據庫)")
                
                # --- 呼叫 Streamlit 內建的寫入邏輯 ---
                if submitted:
                    cleaned_region_name = clean_region_name(new_region)
                    if not all([new_shop_name, cleaned_region_name]): # 檢查必要的欄位
                        st.error("店名、區域不可為空！")
                    else:
                        # 執行寫入
                        add_shop_to_sheet({
                            "shop_name": new_shop_name,
                            "region": cleaned_region_name, # 寫入格式：行政區 - 社區名
                            "item": new_item,
                            "price": new_price,
                            "stock": new_stock,
                            "mode": new_mode, # 固定為剩食
                        })
            
            # 🚀 快速進入商家後台 
            st.divider()
            st.subheader("🚀 快速進入商家後台")
            
            if SHOPS_DB:
                target_shop_admin = st.selectbox("選擇要管理的店家", list(SHOPS_DB.keys()))
                if st.button("進入該店後台"):
                    st.query_params["mode"] = "shop"
                    st.query_params["name"] = target_shop_admin
                    st.rerun()
            else:
                 st.info("目前數據庫中沒有任何店家數據。")
                
            st.divider()
            st.subheader("📱 產生 QR Code")
            if SHOPS_DB:
                qr_shop = st.selectbox("選擇店家 (QR Code)", list(SHOPS_DB.keys()))
                if qr_shop: 
                    shop_link = f"{BASE_APP_URL}/?mode=shop&name={urllib.parse.quote(str(qr_shop))}" 
                    st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(shop_link)}")
                    st.code(shop_link)
                else:
                    st.caption("無法生成 QR Code：店家名稱為空。")
            else:
                st.caption("請先在數據庫中新增店家資料。")

            if st.button("清除應用程式快取"):
                st.cache_data.clear()
                st.rerun()


    # --- 主畫面 (Consumer Logic) ---
    st.title("🍱 友善食光剩食清單 (淡水區)") 
    st.info(f"您的專屬ID：{st.session_state['user_uuid'][:8]}... | 此ID用於預防惡意領取。")
    
    if not SHOPS_DB:
        st.warning("⚠️ 數據庫正在載入中或無法連線，請稍後重試。")
        st.stop()

    # --- 篩選器 (簡化為兩層，聚焦淡水區域) ---
    
    # 獲取所有店家的價格範圍
    all_prices = [v['price'] for v in SHOPS_DB.values() if isinstance(v['price'], int)]
    min_price = int(np.min(all_prices)) if all_prices else 0
    max_price = int(np.max(all_prices)) if all_prices else 100
    if max_price == min_price: max_price += 10 
    
    
    col_filter_1, col_filter_2, col_filter_3 = st.columns([1.5, 1.5, 3]) 

    # 1. 預先篩選出所有淡水相關的完整地區名稱
    all_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
    tamkang_regions = [r for r in all_regions if r.startswith(TAMKANG_PREFIX)]

    # 從淡水區的完整地區名稱中提取社區名稱
    unique_sub_regions = ["所有社區"]
    if tamkang_regions:
        sub_regions_raw = [r.split(' - ')[1].strip() for r in tamkang_regions if ' - ' in r]
        unique_sub_regions = ["所有社區"] + sorted(list(set(sub_regions_raw)))
    
    
    with col_filter_1:
        # Level 1: 社區/次分區篩選
        selected_sub_region = st.selectbox(
            "🏘️ 社區/次分區", 
            unique_sub_regions,
            index=0,
            key="sub_region_selectbox",
            on_change=lambda: st.session_state.update(
                target_shop_select=None 
            )
        )
        
    with col_filter_2:
        # Level 2: 預算區間篩選
        budget_range = st.slider(
            "💲 預算區間",
            min_value=min_price,
            max_value=max_price,
            value=(min_price, max_price),
            step=10,
            key="budget_range"
        )


    # --- 執行最終篩選邏輯 ---
    
    # 1. 執行地區篩選 (固定篩選淡水區內的社區)
    temp_shops = {k: v for k, v in SHOPS_DB.items() if v['region'].startswith(TAMKANG_PREFIX)}
        
    sub_filter_key = clean_region_name(selected_sub_region)
        
    if sub_filter_key != "所有社區":
        full_filter_string = f"{TAMKANG_PREFIX} - {sub_filter_key}"
        temp_shops = {k: v for k, v in temp_shops.items() if v['region'] == full_filter_string}

    # 2. 執行價格篩選
    min_b, max_b = budget_range
    final_filtered_shops = {
        k: v for k, v in temp_shops.items() 
        if v['price'] >= min_b and v['price'] <= max_b
    }

    
    if not final_filtered_shops:
        with col_filter_3:
            st.warning(f"🚨 警告：選定條件下找不到剩食。")
    
    
    # 顯示店家計數
    with col_filter_3:
        st.caption(f"目前顯示 {len(final_filtered_shops)} 個店家。")

    st.divider()

    # --- 顯示人潮多寡列表與連動選擇 (ST.BUTTON) ---
    
    st.subheader("📊 即時剩食清單 (點擊卡片領取)")
    
    shops_with_status = []
    for name, info in final_filtered_shops.items():
        status = get_shop_status(name, info, ORDERS_DF)
        shops_with_status.append({'name': name, 'info': info, 'status': status})
    
    # 排序邏輯：不可用 < 可用
    shops_with_status.sort(key=lambda x: (
        not x['status']['is_available'], 
        -x['status']['current_stock'] # 剩餘多的排前面
    ))
    
    # 顯示列表
    cols_per_row = 3
    if len(shops_with_status) == 0:
        st.info(f"在選定的社區和預算範圍內沒有找到任何剩食項目。")
    else:
        cols = st.columns(cols_per_row)
        
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

            with cols[i % cols_per_row]:
                
                border_color = True
                if st.session_state['target_shop_select'] == name:
                    border_color = "green" 

                # 1. 顯示卡片內容
                with st.container(border=border_color): 
                    st.markdown(f"**🏪 {name}** ({info['region']})") 
                    st.markdown(f"**{status['status_text']}**")
                    
                    st.caption(f"項目：{info['item']} | 價格：**${info['price']}**")

                    if user_is_in_queue:
                        st.success(f"🎉 **您已成功領取！**")
                            
                # 2. 顯示按鈕 (使用普通的 st.button)
                if status['is_available']:
                    if st.button(
                        f"選擇 {name} 領取", 
                        type="primary" if st.session_state['target_shop_select'] != name else "secondary",
                        use_container_width=True,
                        key=f"select_btn_{name}" 
                    ):
                        st.session_state['target_shop_select'] = name
                        st.rerun() # 立即重新執行，實現連動
                        
                else:
                    st.button("❌ 已領取完畢", key=f"unavailable_btn_{name}", disabled=True, use_container_width=True)
            
    # --- 4. 詳細下單/排隊區塊 ---
    
    st.divider()
    
    if st.session_state['target_shop_select'] and st.session_state['target_shop_select'] in final_filtered_shops:
        target_shop_name = st.session_state['target_shop_select']
        
        st.subheader(f"🛒 立即領取 - {target_shop_name}")
        info = final_filtered_shops[target_shop_name]
        status = get_shop_status(target_shop_name, info, ORDERS_DF)
        
        if status['is_available']:
            st.success(f"狀態：{status['status_text']}")
            
            u_name = st.text_input("輸入您的暱稱 (作為取餐依據)", key="u_name_detail")
            
            btn_txt = "🚀 確認領取 (剩食)"
            
            user_has_order = False
            if not ORDERS_DF.empty:
                user_has_order = not ORDERS_DF[(ORDERS_DF['user_id'] == st.session_state['user_uuid']) & (ORDERS_DF['store'] == target_shop_name)].empty
            
            if user_has_order:
                st.warning("⚠️ 您已經領取過了，請勿重複操作。")
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
                                
                                st.success(f"領取成功！請前往 {target_shop_name} 取餐。")
                                st.balloons()
                                st.cache_data.clear()
                                st.session_state['target_shop_select'] = None 
                                st.rerun()
                            else:
                                st.error("操作失敗，請檢查權限設定。")

                        except Exception as e: 
                            st.error(f"連線失敗，請檢查網路或系統狀態。")
                else: st.warning("請輸入名字")

        else:
            st.warning(f"{target_shop_name} 目前已售完或休息中。")
            
    else:
        st.info("⬆️ 請在上方列表點擊卡片選擇店家，進行領取。")
