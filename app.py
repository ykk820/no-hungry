import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse

# ==========================================
# 1. 設定區
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbzDc3IWg8zOPfqlxm-T2zLvr7aEH3scjpr68hF878wLBNl_E8UuCeAqMPPCM75gMwf5kA/exec"
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"
BASE_APP_URL = "https://no-hungry.streamlit.app" 

# ==========================================
# 2. 連線與讀取 (增強除錯功能)
# ==========================================
def get_client():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("❌ 找不到金鑰 (Secrets)，請檢查 Streamlit 設定。")
            return None
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"連線失敗: {e}")
        return None

@st.cache_data(ttl=60)
def load_shops_from_sheet():
    client = get_client()
    if not client: return {}
    
    try:
        # 嘗試開啟檔案
        try:
            sheet_file = client.open_by_key(SPREADSHEET_ID)
        except Exception:
            st.error(f"❌ 無法開啟試算表！請確認 ID: {SPREADSHEET_ID} 是否正確，且權限已開。")
            return {}

        # 嘗試讀取分頁
        try:
            worksheet = sheet_file.worksheet("店家設定")
            data = worksheet.get_all_records()
            
            # 檢查有沒有資料
            if not data:
                st.warning("⚠️ '店家設定' 分頁是空的！請在第二列填入店家資料。")
                return {}
                
            shops_db = {}
            for row in data:
                name = str(row.get('店名', '')).strip()
                if name:
                    shops_db[name] = {
                        'lat': float(row.get('緯度', 0) or 0),
                        'lon': float(row.get('經度', 0) or 0),
                        'item': str(row.get('商品', '優惠商品')),
                        'price': int(row.get('價格', 0) or 0),
                        'stock': int(row.get('初始庫存', 0) or 0)
                    }
            return shops_db

        except gspread.WorksheetNotFound:
            # 🔥 這裡會告訴你它看到了什麼分頁 🔥
            all_sheets = [s.title for s in sheet_file.worksheets()]
            st.error(f"❌ 找不到 '店家設定' 分頁！")
            st.info(f"🔍 系統目前只看到這些分頁：{all_sheets}")
            st.caption("請將 Google Sheet 的分頁名稱改成 '店家設定' (完全一致)。")
            return {}

    except Exception as e:
        st.error(f"讀取發生未知錯誤: {e}")
        return {}

def get_orders():
    client = get_client()
    if not client: return []
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("領取紀錄")
        return sheet.get_all_records()
    except:
        return []

def delete_order(row_index):
    client = get_client()
    if client:
        try:
            sheet = client.open_by_key(SPREADSHEET_ID).worksheet("領取紀錄")
            sheet.delete_rows(row_index + 2)
            return True
        except:
            return False
    return False

# ==========================================
# 3. 主程式
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱", layout="wide")

# 讀取店家資料
SHOPS_DB = load_shops_from_sheet()

# 如果讀不到，啟用「備用模式」讓網頁不要掛掉
if not SHOPS_DB:
    st.warning("⚠️ 進入備用模式 (使用預設測試資料)")
    SHOPS_DB = {
        '測試店家A': {'lat': 25.0330, 'lon': 121.5654, 'item': '測試商品', 'price': 10, 'stock': 99},
    }

# 準備地圖資料
MAP_DATA = pd.DataFrame([
    {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in SHOPS_DB.items()
])

params = st.query_params
current_mode = params.get("mode", "consumer") 
shop_target = params.get("name", None)

# --- 商家後台 ---
if current_mode == "shop" and shop_target in SHOPS_DB:
    st.title(f"🏪 {shop_target} - 後台")
    if st.button("🔄 刷新"):
        st.cache_data.clear()
        st.rerun()
        
    all_orders = get_orders()
    df = pd.DataFrame(all_orders)
    sold_count = 0
    shop_orders = pd.DataFrame()
    if not df.empty:
        shop_orders = df[df.apply(lambda row: shop_target in str(row.values), axis=1)]
        sold_count = len(shop_orders)
    
    initial = SHOPS_DB[shop_target]['stock']
    c1, c2, c3 = st.columns(3)
    c1.metric("庫存", initial)
    c2.metric("已售", sold_count)
    c3.metric("剩餘", initial - sold_count)
    
    st.dataframe(shop_orders)

# --- 消費者 + 管理員 ---
else:
    with st.sidebar:
        st.header("🔒 管理員")
        pwd = st.text_input("密碼", type="password")
        if pwd == "ykk8880820":
            st.success("已登入")
            st.subheader("店家 QR Code")
            sel_shop = st.selectbox("選擇店家", list(SHOPS_DB.keys()))
            link = f"{BASE_APP_URL}/?mode=shop&name={urllib.parse.quote(sel_shop)}"
            st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(link)}")
            st.code(link)
            if st.button("清除快取重整"):
                st.cache_data.clear()
                st.rerun()

    st.title("🍱 餓不死地圖")
    st.map(MAP_DATA, zoom=13)
    
    c1, c2 = st.columns([1, 1.5])
    with c1:
        st.subheader("下單")
        shop = st.selectbox("店家", list(SHOPS_DB.keys()))
        info = SHOPS_DB[shop]
        st.info(f"{info['item']} ${info['price']}")
        name = st.text_input("暱稱")
        if st.button("搶購", type="primary"):
            if name:
                try:
                    requests.post(GAS_URL, json={'user': name, 'item': f"{shop} - {info['item']}"})
                    st.success("成功")
                    st.cache_data.clear()
                except: st.error("失敗")
    
    with c2:
        st.subheader("名單")
        d = get_orders()
        if d:
            df = pd.DataFrame(d)
            if pwd == "ykk8880820":
                # 簡易刪除功能
                del_idx = st.number_input("刪除第幾行(Index)", min_value=0, step=1)
                if st.button("刪除"):
                    delete_order(del_idx)
                    st.rerun()
                st.dataframe(df)
            else:
                st.dataframe(df.tail(10))
