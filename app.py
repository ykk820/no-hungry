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
if 'admin_share_percent' not in st.session_state: 
    st.session_state['admin_share_percent'] = 10.0


# ==========================================
# 1. 系統全域設定 
# ==========================================
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw" # ⚠️ 請更新為您的新 Sheet ID
BASE_APP_URL = "https://no-hungry.streamlit.app"


# ==========================================
# 2. 資料庫連線函式與服務 
# ==========================================

def clean_region_name(name):
    """確保地區名稱乾淨"""
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
        
        # 1. 讀取店家 (假設 Sheet 結構已修正)
        try:
            ws_shops = ss.worksheet("店家設定")
            raw_shops = ws_shops.get_all_records()
            shops_db = {}
            for row in raw_shops:
                name = str(row.get('店名', '')).strip()
                status = str(row.get('狀態', 'Active')).strip()
                
                if name and status.lower() == 'active': 
                    cleaned_region = clean_region_name(row.get('地區', '未分類'))
                    
                    shops_db[name] = {
                        'region': cleaned_region, 
                        'mode': '剩食', 
                        'item': str(row.get('商品名稱', row.get('商品', '優惠商品'))), 
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

# --- 啟用/停用店家功能 (關閉合作) ---
def update_shop_status(shop_name, new_status):
    client = get_client()
    if not client:
        st.error("更新失敗：無法連線至數據庫。")
        return False
    
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet("店家設定")
        cell = ws.find(shop_name, in_column=1) 
        if cell is None:
            st.error("更新失敗：數據庫中找不到該店名。")
            return False
        
        # ⚠️ 假設 '狀態' 在第 9 欄 (I 欄)
        ws.update_cell(cell.row, 9, new_status) 
        
        st.success(f"🚨 {shop_name} 的合作狀態已更新為 **{new_status}**。")
        st.cache_data.clear() 
        st.rerun()
        return True

    except Exception as e:
        st.error(f"更新失敗：寫入數據庫時發生錯誤 ({e})。")
        return False

# --- 簡化後的店家新增函式 (只傳遞核心數據) ---
def add_shop_to_sheet(data):
    
    client = get_client()
    if not client:
        st.error("店家新增失敗。無法連線至數據庫。")
        return False

    # 準備寫入資料 (Lat/Lon 欄位填 0)
    new_row_final = [
        data['region'],      # 1. 地區 (A)
        data['shop_name'],   # 2. 店名 (B)
        data['price'],       # 3. 價格 (C)
        data['stock'],       # 4. 初始庫存 (D)
        data['item'],        # 5. 商品名稱 (E)
        data['mode'],        # 6. 模式 (F)
        0,                   # 7. 經度 (G)
        0,                   # 8. 緯度 (H)
        'Active'             # 9. 狀態 (I)
    ]

    # 執行寫入
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet("店家設定")
        ws.append_row(new_row_final, value_input_option='USER_ENTERED')
        
        st.success(f"✅ 店家 **{data['shop_name']}** 新增成功！")
        st.balloons()
        st.cache_data.clear() # 清除快取
        st.rerun()
    except Exception:
        st.error("新增失敗，請檢查數據庫工作表名稱或權限。")
        return False

def get_shop_status(shop_name, shop_info, orders_df):
    
    claimed_count = 0
    if not orders_df.empty and 'store' in orders_df.columns:
        shop_orders = orders_df[orders_df['store'] == shop_name].copy()
        claimed_count = len(shop_orders)

    current_stock = shop_info['stock'] - claimed_count
    if current_stock < 0: current_stock = 0

    if current_stock > 0:
        status_text = f"📦 **剩餘：{current_stock}** 份"
        is_available = True
    else:
        status_text = "❌ **已售完 / 休息中**"
        is_available = False
        
    return {
        'claimed_count': claimed_count, 
        'current_stock': current_stock,
        'is_available': is_available,
        'status_text': status_text,
    }


# ==========================================
# 3. 頁面開始
# ==========================================
st.set_page_config(page_title="餓不死清單", page_icon="🍱", layout="wide") 

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
    
    with st.sidebar:
        st.title(f"🏪 {shop_target}")
        if st.button("⬅️ 登出 (回首頁)"):
            st.query_params.clear() 
            st.rerun() 
            
        st.divider()
        st.link_button("📄 開啟數據庫", f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit", help="（僅供主管理員參考）")
        st.divider()

        # --- 店家專屬庫存調整面板 ---
        st.subheader("📦 調整今日總庫存")
        with st.form("stock_update_form"):
            current_stock_value = shop_info.get('stock', 0)
            new_stock = st.number_input(
                "設定新的總庫存數量", 
                min_value=0, 
                value=current_stock_value,
                key="new_stock_input"
            )
            if st.form_submit_button("💾 確認更新庫存"):
                if new_stock != current_stock_value:
                    client = get_client()
                    if client:
                        try:
                            ws = client.open_by_key(SPREADSHEET_ID).worksheet("店家設定")
                            cell = ws.find(shop_target, in_column=1) 
                            if cell:
                                # ⚠️ 初始庫存是 D 欄 (第 4 欄)
                                ws.update_cell(cell.row, 4, new_stock) 
                                st.success(f"📦 總庫存已更新為 {new_stock} 份。")
                                st.cache_data.clear() 
                                st.rerun()
                            else:
                                st.error("數據庫中找不到該店名。")
                        except Exception as e:
                            st.error(f"更新失敗：寫入數據庫時發生錯誤 ({e})。")
                    else:
                        st.error("更新失敗：無法連線至數據庫。")
                else:
                    st.warning("庫存數量未改變。")
        # --- END ---

    st.title(f"📊 實時剩食看板 - {shop_target}")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

    shop_orders = pd.DataFrame()
    claimed_count = 0 
    if not ORDERS_DF.empty and 'store' in ORDERS_DF.columns:
        shop_orders = ORDERS_DF[ORDERS_DF['store'] == shop_target].copy()
        claimed_count = len(shop_orders)
    
    c1, c2, c3 = st.columns(3)
    remain = shop_info['stock'] - claimed_count
    c1.metric("📦 總庫存", shop_info['stock'])
    c2.metric("✅ 已領取", claimed_count)
    c3.metric("🔥 剩餘", remain, delta_color="inverse")
    
    st.divider()
    st.subheader("📋 待處理領取名單")
    
    if not shop_orders.empty:
        shop_orders_display = shop_orders.reset_index().rename(columns={'index': 'original_index'})
        shop_orders_display['號碼牌'] = range(1, len(shop_orders_display) + 1)
        
        st.write("🛠️ 管理員操作")
        del_opts = [f"{r['original_index']}:{r['號碼牌']}. {r.get('user', '?')} - {r.get('item', '?')}" for i, r in shop_orders_display.iterrows()]
        target_del = st.selectbox("完成領取/刪除訂單", del_opts, key="admin_shop_order_select")
        
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
            
            # --- 啟用/停用店家功能 (關閉合作) ---
            st.subheader("🛑 合作管理 (啟用/停用)")
            if SHOPS_DB:
                shop_to_manage = st.selectbox("選擇要管理的店家", list(SHOPS_DB.keys()), key="admin_manage_shop_select")
                
                status_opts = ["Active", "Inactive"]
                
                new_status = st.selectbox("設定新狀態", status_opts, index=0, key="admin_manage_status") 
                
                if st.button("🔄 更新店家狀態", type="primary"):
                    update_shop_status(shop_to_manage, new_status)
            else:
                st.info("數據庫中沒有店家可供管理。")
            
            st.divider()
            
            # --- 財務追蹤面板 (抽成比例與計算) ---
            st.subheader("💰 收入追蹤")
            
            # 輸入抽成比例
            share_percent = st.number_input(
                "您的抽成比例 (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=st.session_state['admin_share_percent'],
                key="share_percent_input_main"
            )
            st.session_state['admin_share_percent'] = share_percent
            
            total_claimed_revenue = 0
            total_items_claimed = len(ORDERS_DF)
            
            # 計算總收入
            if not ORDERS_DF.empty:
                for _, order_row in ORDERS_DF.iterrows():
                    shop_name = order_row['store']
                    if shop_name in SHOPS_DB:
                        price = SHOPS_DB[shop_name]['price']
                        total_claimed_revenue += price
            
            admin_share_value = total_claimed_revenue * (share_percent / 100)
            
            st.metric("✅ 總領取訂單數", total_items_claimed)
            st.metric("💲 預計總銷售額", f"${total_claimed_revenue}")
            st.metric("💰 應抽收入 (預估)", f"${admin_share_value:,.2f}")
            
            st.divider()
            
            # --- 管理員新增店家表單邏輯 ---
            st.subheader("➕ 新增店家")
            st.caption("請確保 Google Sheet 欄位順序為：地區, 店名, 價格, 初始庫存, 商品名稱, 模式, 經度, 緯度, 狀態。")
            with st.form("add_shop_form"):
                col_a, col_b = st.columns(2)
                with col_a:
                    new_shop_name = st.text_input("店名*", key="new_shop_name")
                    new_item = st.text_input("商品名*", key="new_item", value="剩食套餐")
                    new_price = st.number_input("價格*", min_value=1, value=50) # 價格輸入
                with col_b:
                    
                    # --- FIX: 只能選擇現有地區 ---
                    all_existing_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
                    
                    # 判斷是否還有地區可選
                    if all_existing_regions:
                        new_region = st.selectbox(
                            "選擇現有地區*", 
                            all_existing_regions,
                            key="new_region_select"
                        )
                    else:
                        # 允許管理員手動輸入第一個地區
                        new_region = st.text_input(
                             "地區名稱*", 
                             key="new_region_manual", 
                             value="請在此輸入第一個地區名稱",
                             help="請確保名稱標準化，例：新北市淡水區淡江大學"
                        )

                    new_stock = st.number_input("初始庫存", min_value=1, value=10)
                
                new_mode = '剩食' # 固定為剩食模式
                
                submitted = st.form_submit_button("✅ 新增店家 (直接寫入數據庫)")
                
                # --- 呼叫 Streamlit 內建的寫入邏輯 ---
                if submitted:
                    
                    # 修正：確保取得的是 selectbox 或 text_input 的值
                    if all_existing_regions:
                         submitted_region = st.session_state['new_region_select']
                    else:
                         submitted_region = st.session_state['new_region_manual']
                         
                    cleaned_region_name = clean_region_name(submitted_region)
                    
                    if not all([new_shop_name, cleaned_region_name]): 
                        st.error("店名、地區不可為空！")
                    elif cleaned_region_name == "請在此輸入第一個地區名稱":
                        st.error("請輸入有效的地區名稱。")
                    else:
                        # 執行寫入
                        add_shop_to_sheet({
                            "shop_name": new_shop_name,
                            "region": cleaned_region_name, 
                            "item": new_item,
                            "price": new_price,
                            "stock": new_stock,
                            "mode": new_mode, 
                        })
            
            # 🚀 快速進入商家後台 
            st.divider()
            st.subheader("🚀 快速進入商家後台")
            
            if SHOPS_DB:
                target_shop_admin = st.selectbox("選擇要管理的店家", list(SHOPS_DB.keys()), key="admin_quick_access_select")
                if st.button("進入該店後台"):
                    st.query_params["mode"] = "shop"
                    st.query_params["name"] = target_shop_admin
                    st.rerun()
            else:
                 st.info("目前數據庫中沒有任何店家數據。")
                
            # --- 批量二維碼生成邏輯 ---
            st.divider()
            st.subheader("📱 批量二維碼")
            if st.button("查看所有二維碼"):
                st.session_state['show_bulk_qr'] = True
            
            if st.button("清除應用程式快取"):
                st.cache_data.clear()
                st.rerun()


    # --- 主畫面 (Consumer Logic) ---
    st.title("🍱 剩食超人") 
    st.info(f"您的專屬ID：{st.session_state['user_uuid'][:8]}... | 此ID用於預防惡意領取。")
    
    if not SHOPS_DB:
        st.warning("⚠️ 數據庫正在載入中或無法連線，請稍後重試。")
        st.stop()
        
    # --- 批量二維碼生成區塊 (管理員登入後顯示) ---
    if is_admin and st.session_state.get('show_bulk_qr'):
        st.header("📱 所有店家二維碼連結 (批量)")
        if SHOPS_DB:
            
            # 將所有店家數據按地區分組 (消費者介面的分類)
            shops_by_region = {}
            for name, info in SHOPS_DB.items():
                region = info['region']
                if region not in shops_by_region:
                    shops_by_region[region] = {}
                shops_by_region[region][name] = info

            # 依地區迭代顯示
            sorted_regions = sorted(shops_by_region.keys())
            for region_name in sorted_regions:
                st.subheader(f"區域：{region_name}")
                
                qr_cols = st.columns(5)
                for i, (name, info) in enumerate(shops_by_region[region_name].items()):
                    shop_link = f"{BASE_APP_URL}/?mode=shop&name={urllib.parse.quote(str(name))}"
                    qr_img_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(shop_link)}"
                    
                    with qr_cols[i % 5]:
                        st.markdown(f"**{name}** ({info['region'].split(' - ')[-1]})")
                        st.image(qr_img_url, caption=f"掃描進入看板", width=120)
                        st.caption(f"連結: [Link]({shop_link})")
                        st.write("---")
            
            if st.button("返回主頁"):
                st.session_state['show_bulk_qr'] = False
                st.rerun()

            st.stop() # 停止執行後續的消費者介面
    # --- END 批量二維碼生成區塊 ---


    # --- 篩選器 (單層地區篩選 + 預算) ---
    
    # 獲取所有店家的價格範圍
    all_prices = [v['price'] for v in SHOPS_DB.values() if isinstance(v['price'], int)]
    min_price = int(np.min(all_prices)) if all_prices else 0
    max_price = int(np.max(all_prices)) if all_prices else 100
    if max_price == min_price: max_price += 10
    
    
    col_filter_1, col_filter_2 = st.columns([1, 1]) 

    # 獲取所有地區名稱 (單層)
    all_regions = sorted(list(set([v['region'] for v in SHOPS_DB.values()])))
    
    
    with col_filter_1:
        # 地區篩選
        selected_region = st.selectbox(
            "📍 選擇地區", 
            ["所有地區"] + all_regions,
            index=0,
            key="region_selectbox",
            on_change=lambda: st.session_state.update(
                target_shop_select=None 
            )
        )
        
    with col_filter_2:
        # 預算區間篩選
        budget_range = st.slider(
            "💲 預算區間",
            min_value=min_price,
            max_value=max_price,
            value=(min(50, max_price), min(100, max_price)), # 設置預設值 50-100
            step=10,
            key="budget_range"
        )


    # --- 執行最終篩選邏輯 ---
    
    # 1. 執行地區篩選 (單層)
    selected_filter_key = clean_region_name(selected_region)
    
    if selected_filter_key == "所有地區":
        temp_shops = SHOPS_DB
    else:
        temp_shops = {k: v for k, v in SHOPS_DB.items() if v['region'] == selected_filter_key}

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

    # --- 顯示剩食清單 (ST.BUTTON) ---
    
    st.subheader("📊 即時剩食清單 (點擊卡片領取)")
    
    shops_with_status = []
    for name, info in final_filtered_shops.items():
        status = get_shop_status(name, info, ORDERS_DF)
        shops_with_status.append({'name': name, 'info': info, 'status': status})
    
    # 排序邏輯：不可用 < 可用
    shops_with_status_sorted = []
    for item in shops_with_status:
        shops_with_status_sorted.append({
            'name': item['name'],
            'info': item['info'],
            'status': item['status'],
            'sort_key': (not item['status']['is_available'], -item['status']['current_stock'])
        })

    shops_with_status_sorted.sort(key=lambda x: x['sort_key'])


    # 顯示列表
    cols_per_row = 3
    if len(shops_with_status_sorted) == 0:
        st.info(f"在選定的地區和預算範圍內沒有找到任何剩食項目。")
    else:
        
        # 依地區分組顯示 (消費者介面)
        shops_by_region_consumer = {}
        for item in shops_with_status_sorted:
            name = item['name']
            info = item['info']
            status = item['status']
            region = info['region']
            if region not in shops_by_region_consumer:
                shops_by_region_consumer[region] = {}
            
            shops_by_region_consumer[region][name] = info
            
        sorted_regions_consumer = sorted(shops_by_region_consumer.keys())
        
        for region_name in sorted_regions_consumer:
            st.markdown(f"### {region_name} 區域 ({len(shops_by_region_consumer[region_name])} 店)")
            
            cols = st.columns(cols_per_row)
            
            for i, (name, info) in enumerate(shops_by_region_consumer[region_name].items()):
                
                status = get_shop_status(name, info, ORDERS_DF)
                
                user_has_claimed = False
                if 'user_id' in ORDERS_DF.columns and 'store' in ORDERS_DF.columns:
                    my_claim = ORDERS_DF[(ORDERS_DF['user_id'] == st.session_state['user_uuid']) & (ORDERS_DF['store'] == name)]
                    if not my_claim.empty:
                        user_has_claimed = True

                with cols[i % cols_per_row]:
                    
                    border_color = True
                    if st.session_state['target_shop_select'] == name:
                        border_color = "green" 

                    # 1. 顯示卡片內容
                    with st.container(border=border_color): 
                        st.markdown(f"**🏪 {name}**") 
                        st.markdown(f"**{status['status_text']}**")
                        
                        st.caption(f"項目：{info['item']} | 價格：**${info['price']}**")

                        if user_has_claimed: # 使用新的變數名
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
            
    # --- 4. 詳細領取區塊 ---
    
    st.divider()
    
    if st.session_state['target_shop_select'] and st.session_state['target_shop_select'] in final_filtered_shops:
        target_shop_name = st.session_state['target_shop_select']
        
        st.subheader(f"🛒 立即領取 - {target_shop_name}")
        info = final_filtered_shops[target_shop_name]
        status = get_shop_status(target_shop_name, info, ORDERS_DF)
        
        if status['is_available']:
            st.success(f"狀態：{status['status_text']}")
            
            u_name = st.text_input("輸入您的暱稱 (作為取餐依據)", key="u_name_detail")
            
            btn_txt = "🚀 確認領取"
            
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

                        except Exception: 
                            st.error(f"連線失敗，請檢查網路或系統狀態。")
                else: st.warning("請輸入名字")

        else:
            st.warning(f"{target_shop_name} 目前已售完或休息中。")
            
    else:
        st.info("⬆️ 請在上方列表點擊卡片選擇店家，進行領取。")
