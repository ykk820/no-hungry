import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import time
import uuid
from datetime import datetime, timedelta
import math
from streamlit_js_eval import get_geolocation
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- 1. 系統配置 ---
st.set_page_config(page_title="餓不死系統", page_icon="🍱", layout="wide")
st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>""", unsafe_allow_html=True)

# --- 2. Google Sheets 連線模組 (核心) ---
@st.cache_resource
def init_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 從 Streamlit Secrets 讀取金鑰
    # 注意：這裡假設你在 Secrets 裡面的區塊名稱叫 [gcp_service_account]
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # 修正 private_key 的換行問題 (有些 copy paste 會出錯)
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_data():
    """從 Google Sheets 讀取所有資料"""
    client = init_connection()
    try:
        # 記得把這裡改成你的試算表名稱
        sheet = client.open("餓不死資料庫") 
        
        # 讀取三個分頁
        shops_data = sheet.worksheet("shops").get_all_records()
        inventory_data = sheet.worksheet("inventory").get_all_records()
        users_data = sheet.worksheet("users").get_all_records()
        
        return shops_data, inventory_data, users_data, sheet
    except Exception as e:
        st.error(f"連線失敗：{e}")
        return [], [], [], None

# 初始化：將 Sheet 資料轉為我們習慣的字典格式
# 為了效能，我們讀取一次後暫存，寫入時再回傳 Sheet
raw_shops, raw_inv, raw_users, sheet_obj = get_data()

# --- 資料轉換 (Sheet List -> Dictionary) ---
# 這裡需要一點轉換工法，因為 Sheet 讀下來是 List，我們程式用的是 Dictionary
db = {
    "shops": {str(row['id']): row for row in raw_shops},
    "inventory": raw_inv,
    "users": {str(row['email']): row for row in raw_users},
    "sheet_obj": sheet_obj # 把連線物件存起來方便寫入
}

# --- 資料寫入輔助函式 (Sync to Cloud) ---
def sync_shops_to_cloud():
    """將店家資料寫回雲端"""
    if not db["sheet_obj"]: return
    ws = db["sheet_obj"].worksheet("shops")
    # 轉回 List of Lists
    data = [list(db["shops"][k].values()) for k in db["shops"]]
    # 這裡簡化處理：直接清空重寫 (少量資料適用)
    ws.clear()
    ws.append_row(['id', 'name', 'key', 'school', 'location', 'map_url', 'lat', 'lon', 'queue_status']) # Header
    # 這裡需要確保欄位順序一致，建議進階版改用 dataframe寫入
    # 為了 MVP 穩定，這裡先用 append_rows (需確保字典順序)
    # (實作上如果欄位多，建議用 Pandas + gspread-dataframe，這裡先維持簡單)
    # 暫時略過複雜寫入，採用「有動作就插入一行」的策略比較安全
    pass 

def add_shop_to_cloud(shop_data):
    ws = db["sheet_obj"].worksheet("shops")
    ws.append_row(list(shop_data.values()))

def add_item_to_cloud(item_data):
    ws = db["sheet_obj"].worksheet("inventory")
    ws.append_row(list(item_data.values()))

def update_inventory_cloud():
    # 全量更新庫存 (適合資料量少時)
    ws = db["sheet_obj"].worksheet("inventory")
    ws.clear()
    ws.append_row(['id', 'shop_id', 'item', 'price', 'qty', 'desc', 'time'])
    rows = [list(x.values()) for x in db["inventory"]]
    if rows: ws.append_rows(rows)

# --- 3. 自動化模組 (3AM 重置) ---
# 注意：接了 Google Sheets 後，重置邏輯要改成「寫入雲端」
# 為了避免太複雜，這裡先維持記憶體重置，等你下次按按鈕時再同步

# --- 4. 工具模組 ---
def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue()

def get_time_string():
    return datetime.now().strftime("%H:%M")

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

TKU_LOCATIONS = {
    "大學城 (Hi-City)": {"lat": 25.1765, "lon": 121.4425},
    "水源街 (圖書館側)": {"lat": 25.1735, "lon": 121.4440},
    "大田寮 (操場側)": {"lat": 25.1710, "lon": 121.4460},
    "捷運站周邊": {"lat": 25.1678, "lon": 121.4456},
    "其他 (自訂座標)": {"lat": 25.1750, "lon": 121.4430}
}

# --- 5. 介面模組 ---
# (為了版面簡潔，介面邏輯大部分與 v9.0 相同，但加上了寫入雲端的動作)

# [A] 軍師後台
def view_admin():
    st.title("🛠️ 餓不死系統 - 雲端指揮中心")
    
    # 檢查連線
    if db["sheet_obj"]:
        st.success("☁️ Google Sheets 資料庫：連線成功")
    else:
        st.error("☁️ 資料庫連線失敗，請檢查 Secrets 設定")

    with st.expander("➕ 新增合作店家", expanded=True): 
        with st.form("add_shop"):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("店家名稱")
            location_zone = c2.selectbox("所在區域", list(TKU_LOCATIONS.keys()))
            default_lat = TKU_LOCATIONS[location_zone]["lat"]
            default_lon = TKU_LOCATIONS[location_zone]["lon"]
            c3, c4 = st.columns(2)
            map_url = c3.text_input("Google Maps 連結", placeholder="選填")
            
            if st.form_submit_button("建立"):
                if new_name:
                    new_id = str(uuid.uuid4())[:8]
                    new_key = str(uuid.uuid4())
                    
                    new_shop_data = {
                        "id": new_id,
                        "name": new_name, 
                        "key": new_key,
                        "school": "淡江大學",
                        "location": location_zone,
                        "map_url": map_url if map_url else f"https://www.google.com/maps/search/?api=1&query={new_name}+淡江大學",
                        "lat": default_lat,
                        "lon": default_lon,
                        "queue_status": "🟢 免排隊"
                    }
                    
                    # 更新記憶體
                    db["shops"][new_id] = new_shop_data
                    # 同步到雲端
                    add_shop_to_cloud(new_shop_data)
                    
                    st.success(f"✅ {new_name} 建立成功 (已存入雲端)！")
                    time.sleep(0.5)
                    st.rerun()

    st.divider()

    # 店家列表
    if not db["shops"]:
        st.warning("⚠️ 目前無店家資料。")
    else:
        st.markdown("### 📋 店家列表")
        # 從 Secrets 或代碼中硬編碼 Base URL (這裡簡化處理)
        base_url = "https://tku-food.streamlit.app" # 請改成你的網址
        
        for s_id, info in db["shops"].items():
            with st.container(border=True):
                col_a, col_b, col_c = st.columns([1, 2, 1])
                full_qr_url = f"{base_url}/?shop_key={info['key']}"
                
                with col_a:
                    st.image(generate_qr_code(full_qr_url), width=100)
                with col_b:
                    st.subheader(info['name'])
                    st.caption(f"📍 {info['location']}")
                with col_c:
                    if st.button("進入店家模式 ➜", key=f"enter_{s_id}"):
                        st.query_params["shop_key"] = info['key']
                        st.rerun()

# [B] 店家端
def view_shop(shop_id):
    shop_info = db["shops"].get(shop_id)
    if not shop_info:
        st.error("資料庫讀取錯誤")
        return

    my_items = [x for x in db["inventory"] if str(x['shop_id']) == str(shop_id)]
    total_qty = sum([int(x['qty']) for x in my_items])
    is_open = total_qty > 0

    c_title, c_btn = st.columns([3, 1])
    with c_title:
        st.title(f"👨‍🍳 {shop_info['name']}")
        st.info(f"📢 狀態：**{shop_info.get('queue_status', '免排隊')}**")
    with c_btn:
        if st.button("登出"): st.query_params.clear(); st.rerun()

    st.divider()
    col_status, col_action = st.columns([2, 1])
    with col_status:
        if is_open: st.success(f"🟢 **營業中** (剩 {total_qty} 份)")
        else: st.info("⚫ **已打烊**")
            
    with col_action:
        if is_open:
            if st.button("🌙 打烊/清空", type="primary", use_container_width=True):
                # 記憶體清空
                db["inventory"] = [x for x in db["inventory"] if str(x['shop_id']) != str(shop_id)]
                # 雲端同步
                update_inventory_cloud()
                st.rerun()

    st.divider()
    st.subheader("🚀 上架")
    with st.container(border=True):
        with st.form("add_item"):
            f1, f2 = st.columns(2)
            item_name = f1.text_input("品項")
            item_price = f2.number_input("價格", value=60)
            item_qty = st.number_input("數量", value=5, min_value=1)
            item_desc = st.text_input("備註")
            
            if st.form_submit_button("確認上架"):
                new_item = {
                    "id": str(uuid.uuid4())[:6],
                    "shop_id": shop_id,
                    "item": item_name,
                    "price": item_price,
                    "qty": item_qty,
                    "desc": item_desc,
                    "time": get_time_string()
                }
                db["inventory"].append(new_item)
                add_item_to_cloud(new_item)
                st.success("上架成功！")
                time.sleep(0.5)
                st.rerun()

    # 商品列表 (顯示略)
    if my_items:
        for item in my_items:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{item['item']}** (${item['price']})")
                if c2.button("🗑️ 刪", key=f"del_{item['id']}"):
                    db["inventory"].remove(item)
                    update_inventory_cloud()
                    st.rerun()

# [C] 學生端 (簡化版)
def view_student():
    st.title("🍱 餓不死地圖 (雲端版)")
    
    # GPS 
    loc = get_geolocation(component_key='user_loc')
    user_lat, user_lon = None, None
    if loc and 'coords' in loc:
        user_lat = loc['coords']['latitude']
        user_lon = loc['coords']['longitude']

    # Tab 邏輯同 v9.0，這裡省略重複代碼，重點是資料來源改為 db["inventory"]
    # ... (請將 v9.0 的 view_student 複製過來，邏輯通用的)
    # 唯一要注意的是：搶購扣庫存時，記得呼叫 update_inventory_cloud()
    
    st.info("🚧 (為了代碼長度，請直接套用 v9.0 的學生端邏輯，只需在搶購成功後加上 update_inventory_cloud())")


# --- 路由 ---
shop_key = st.query_params.get("shop_key", None)
test_mode = st.query_params.get("test_mode", None)

target_shop = None
if shop_key:
    for s_id, info in db["shops"].items():
        if str(info['key']) == str(shop_key):
            target_shop = s_id
            break

if target_shop:
    view_shop(target_shop)
elif test_mode == "student":
    view_student()
else:
    if st.session_state.get("is_admin_logged_in"):
        view_admin()
    else:
        with st.sidebar:
            st.divider()
            with st.expander("🔧 系統管理"):
                if st.text_input("密碼", type="password") == "ykk8880820":
                    if st.button("進入"):
                        st.session_state.is_admin_logged_in = True
                        st.rerun()
        view_student()
