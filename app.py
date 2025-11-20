import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse
from datetime import datetime
import uuid 

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

# --- 區域標準化名稱 (格式：[行政區] - [社區名]) ---
SUGGESTED_REGIONS_FULL = [
    '新北市淡水區 - 淡江大學',
    '新北市淡水區 - 金雞母/水源街',
    '新北市淡水區 - 大田寮',
    '新北市淡水區 - 英專路/老街',
    '新北市淡水區 - 淡海新市鎮',
    '新北市淡水區 - 紅樹林/竹圍',
    '台北市大安區 - 師大夜市',
    '台北市信義區 - 市政府'
]

# ==========================================
# 2. 資料庫連線函式與服務 (移除 Lat/Lon 依賴)
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
                        # ⚠️ 徹底移除 Lat/Lon 讀取
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

# --- 簡化後的店家新增函式 (移除 Lat/Lon 參數) ---
def add_shop_to_sheet(data):
    
    client = get_client()
    if not client:
        st.error("店家新增失敗。無法連線至 Google Sheets (請檢查 GCP 服務帳戶金鑰)")
        return False

    # 準備寫入資料 (注意：new_row 必須與 Google Sheet 欄位順序一致，Lat/Lon 欄位填 0)
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
    except Exception as e:
        st.error(f"寫入 Google Sheet 失敗: {str(e)}。請檢查工作表名稱或權限。")
        return False

def get_shop_status(shop_name, shop_info, orders_df):
    if orders_df.empty or 'store' not in orders_df.columns:
        queue_count = 0
    else:
        shop_orders = orders_df[shop_orders.index[-1]].copy() # 修正：這裡的篩選邏輯需要修正
        # 由於 get_shop_status 的 orders_df 參數可能已被過濾，這裡應該使用外部的 ALL_ORDERS 或修正篩選方式
        
        # 採用修正後的篩選，使用傳入的 shop_target 確保訂單正確
        if 'store' in ORDERS_DF.columns:
            shop_orders = ORDERS_DF[ORDERS_DF['store'] == shop_name].copy()
            queue_count = len(shop_orders)
        else:
            # 安全回退
             queue_count = 0


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
            # 從 SUGGESTED_REGIONS_FULL 提取行政區和社區名
            unique_main_regions = sorted(list(set([r.split(' - ')[0].strip() for r in SUGGESTED_REGIONS_FULL])))
            
            st.subheader("➕ 一鍵新增店家 (手動輸入坐標)")
            st.caption("請手動將經緯度設為 0, 0 或輸入您已知的精確坐標")
            with st.form("add_shop_form"):
                col_a, col_b = st.columns(2)
                with col_a:
                    new_shop_name = st.text_input("店名*", key="new_shop_name")
                    new_item = st.text_input("商品名*", key="new_item", value="剩食套餐")
                    new_price = st.number_input("價格*", min_value=1, value=50)
                with col_b:
                    # ⚠️ 移除地址定位，改為手動輸入經緯度
                    new_lat = st.number_input("緯度 (Lat)*", value=0.0, help="例如: 25.1764 (如不需要可填 0)")
                    new_lon = st.number_input("經度 (Lon)*", value=0.0, help="例如: 121.4498 (如不需要可填 0)")

                    # --- FIX: 雙層地區選擇輸入 ---
                    selected_main_region = st.selectbox(
                        "選擇行政區*", 
                        ["新增行政區..."] + unique_main_regions,
                    )
                    
                    if selected_main_region == "新增行政區...":
                        main_region = st.text_input("輸入新行政區名稱", key="new_main_region_manual", value="") 
                    else:
                        main_region = selected_main_region

                    sub_region = st.text_input("輸入社區/次分區名稱*", key="new_sub_region_manual", value="", help="例如：金雞母/水源街")

                    # 將兩級地區合併為單一字串
                    new_region = f"{main_region} - {sub_region}" if main_region and sub_region else ""
                    # ---------------------------

                    new_stock = st.number_input("初始庫存", min_value=1, value=10)
                
                new_mode_options = ['剩食', '排隊']
                new_mode = st.selectbox("營運模式", new_mode_options, index=new_mode_options.index('剩食'))
                
                submitted = st.form_submit_button("✅ 新增店家 (直接寫入 Sheet)")
                
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
                            "mode": new_mode,
                            "lat": new_lat, # 傳入緯度 (佔位)
                            "lon": new_lon  # 傳入經度 (佔位)
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
                 st.info("目前 Google Sheet 中沒有任何店家數據。")
                
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
                st.caption("請先在 Google Sheet 中新增店家資料。")

            if st.button("清除快取"):
                st.cache_data.clear()
                st.rerun()


    # --- 主畫面 (Consumer Logic) ---
    st.title("🍱 餓不死清單") # 更改標題
    st.info(f"您的唯一ID：{st.session_state['user_uuid'][:8]}... | 此ID用於防範棄單。")
    
    if not SHOPS_DB:
        st.warning("⚠️ 無法讀取店家資料，請檢查 Google Sheet 設定。")
        st.stop()

    # --- 篩選器與狀態管理 ---
    all_full_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
    
    # 從完整的地區名稱中提取第一級行政區
    unique_main_regions = sorted(list(set([r.split(' - ')[0].strip() for r in all_full_regions if ' - ' in r])))
    
    # 初始化篩選狀態
    if 'main_region_select' not in st.session_state:
         st.session_state['main_region_select'] = "所有區域"

    # --- 雙層篩選器 ---
    col_filter_1, col_filter_2, col_filter_3 = st.columns([1, 1, 3])

    with col_filter_1:
        # Level 1: 行政區篩選
        selected_main_region = st.selectbox(
            "📍 行政區", 
            ["所有區域"] + unique_main_regions,
            index=0,
            key="main_region_selectbox",
            on_change=lambda: st.session_state.update(
                main_region_select=st.session_state.main_region_selectbox,
                target_shop_select=None 
            )
        )
    
    # 過濾 Level 2 選項
    main_filter_key = clean_region_name(st.session_state['main_region_select'])
    sub_regions = ["所有社區"]
    
    if main_filter_key != "所有區域":
        # 獲取符合 Level 1 的所有 Level 2 社區名稱
        sub_regions_raw = [r.split(' - ')[1].strip() for r in all_full_regions if r.startswith(main_filter_key)]
        sub_regions = ["所有社區"] + sorted(list(set(sub_regions_raw)))

    with col_filter_2:
        # Level 2: 社區篩選
        selected_sub_region = st.selectbox(
            "🏘️ 社區/次分區", 
            sub_regions,
            index=0,
            key="sub_region_selectbox",
            on_change=lambda: st.session_state.update(
                target_shop_select=None 
            )
        )

    # --- 執行最終篩選 ---
    final_filtered_shops = {}
    
    if main_filter_key == "所有區域":
        final_filtered_shops = SHOPS_DB
    else:
        # 先按 Level 1 篩選
        temp_shops = {k: v for k, v in SHOPS_DB.items() if v['region'].startswith(main_filter_key)}
        
        sub_filter_key = clean_region_name(selected_sub_region)
        
        if sub_filter_key == "所有社區":
            final_filtered_shops = temp_shops
        else:
            # 按完整的 [行政區 - 社區名] 進行篩選
            full_filter_string = f"{main_filter_key} - {sub_filter_key}"
            final_filtered_shops = {k: v for k, v in temp_shops.items() if v['region'] == full_filter_string}

    
    if not final_filtered_shops and main_filter_key != "所有區域":
        st.warning(f"🚨 警告：選定區域 **{main_filter_key}** 下找不到店家。請檢查 Google Sheet 中的地區名稱是否完全一致。")
    
    
    # 移除地圖顯示
    with col_filter_3:
        st.caption("請在左側選單篩選區域，下方查看店家清單。")

    st.divider()

    # --- 顯示人潮多寡列表與連動選擇 (ST.BUTTON) ---
    
    st.subheader("📊 即時人潮狀態一覽 (點擊卡片選擇店家)")
    
    shops_with_status = []
    for name, info in final_filtered_shops.items():
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
        st.info(f"在選定的區域內沒有找到任何店家。")
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
                    shop_orders = ORDERS_DF[ORDERS_DF['store'] == name]
                    my_order_index = my_queue.index[0]
                    my_queue_number = len(shop_orders[shop_orders.index <= my_order_index])


            with cols[i % cols_per_row]:
                
                border_color = True
                if st.session_state['target_shop_select'] == name:
                    border_color = "green" 

                # 1. 顯示卡片內容
                with st.container(border=border_color): 
                    # ⚠️ 顯示完整的地區名稱
                    st.markdown(f"**🏪 {name}** ({info['region']})") 
                    st.markdown(f"**{status['status_text']}**")
                    
                    if status['is_queue_mode']:
                        st.caption(f"模式：餐期排隊 | 叫號依據：**{info['item']}**")
                    elif status['is_available']:
                        st.caption(f"模式：剩食 | 價格：**${info['price']}**")

                    if user_is_in_queue:
                        st.success(f"🎉 **您排在 {my_queue_number} 號！**")
                            
                # 2. 顯示按鈕 (使用普通的 st.button)
                if status['is_available']:
                    if st.button(
                        f"選擇 {name} 進行下單", 
                        type="primary" if st.session_state['target_shop_select'] != name else "secondary",
                        use_container_width=True,
                        key=f"select_btn_{name}" 
                    ):
                        st.session_state['target_shop_select'] = name
                        st.rerun() # 立即重新執行，實現連動
                        
                else:
                    st.button("休息中 / 已售完", key=f"unavailable_btn_{name}", disabled=True, use_container_width=True)
            
    # --- 4. 詳細下單/排隊區塊 ---
    
    st.divider()
    
    if st.session_state['target_shop_select'] and st.session_state['target_shop_select'] in final_filtered_shops:
        target_shop_name = st.session_state['target_shop_select']
        
        st.subheader(f"🛒 立即排隊/搶購 - {target_shop_name}")
        info = final_filtered_shops[target_shop_name]
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
            
    elif st.session_state['target_shop_select'] and st.session_state['target_shop_select'] not in final_filtered_shops:
        st.warning("您選擇的店家不在當前區域篩選結果中，請重新選擇。")
        st.session_state['target_shop_select'] = None
    
    else:
        st.info("⬆️ 請在上方列表點擊卡片選擇店家，進行下單或排隊。")
