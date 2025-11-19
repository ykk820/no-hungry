import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse

# ==========================================
# 1. 設定區
# ==========================================
# 你的 GAS 網址
GAS_URL = "https://script.google.com/macros/s/AKfycbzDc3IWg8zOPfqlxm-T2zLvr7aEH3scjpr68hF878wLBNl_E8UuCeAqMPPCM75gMwf5kA/exec"

# 你的 Google Sheet ID (不變)
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"

# 你的 APP 網址 (請在這裡填入你發布後的真正網址，這樣 QR Code 才會對)
# 例如: https://no-hungry.streamlit.app
BASE_APP_URL = "https://no-hungry.streamlit.app" 

# ==========================================
# 2. 連線 Google Sheet
# ==========================================
def get_client():
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception:
        return None

@st.cache_data(ttl=60) # 設定快取 60 秒，避免一直讀取變慢
def load_shops_from_sheet():
    """從 Google Sheet '店家設定' 分頁讀取店家資料"""
    client = get_client()
    if not client: return {}
    
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("店家設定")
        data = sheet.get_all_records()
        
        shops_db = {}
        for row in data:
            # 確保欄位名稱對應 (Google Sheet 的標題)
            name = str(row.get('店名', '')).strip()
            if name:
                shops_db[name] = {
                    'lat': float(row.get('緯度', 0)),
                    'lon': float(row.get('經度', 0)),
                    'item': str(row.get('商品', '優惠商品')),
                    'price': int(row.get('價格', 0)),
                    'stock': int(row.get('初始庫存', 0))
                }
        return shops_db
    except Exception as e:
        st.error(f"讀取店家設定失敗: {e}")
        return {}

def get_orders():
    """讀取 '領取紀錄'"""
    client = get_client()
    if not client: return []
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("領取紀錄")
        return sheet.get_all_records()
    except:
        return []

def delete_order(row_index):
    """刪除訂單"""
    client = get_client()
    if client:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("領取紀錄")
        sheet.delete_rows(row_index + 2)
        return True
    return False

# ==========================================
# 3. 主程式邏輯
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱", layout="wide")

# 讀取店家資料 (現在是動態的了！)
SHOPS_DB = load_shops_from_sheet()

if not SHOPS_DB:
    st.error("⚠️ 無法讀取店家資料，請確認 Google Sheet 有 '店家設定' 分頁且已填寫。")
    st.stop()

# 準備地圖資料
MAP_DATA = pd.DataFrame([
    {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in SHOPS_DB.items()
])

# 處理網址參數
params = st.query_params
current_mode = params.get("mode", "consumer") 
shop_target = params.get("name", None)

# ------------------------------------------
# 🔵 模式 A: 商家後台 (掃碼進入)
# ------------------------------------------
if current_mode == "shop" and shop_target in SHOPS_DB:
    st.title(f"🏪 {shop_target} - 商家後台")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()
    
    # 計算庫存
    all_orders = get_orders()
    df = pd.DataFrame(all_orders)
    
    sold_count = 0
    shop_orders = pd.DataFrame()
    
    if not df.empty:
        # 篩選出該店家的訂單
        shop_orders = df[df.apply(lambda row: shop_target in str(row.values), axis=1)]
        sold_count = len(shop_orders)
        
    shop_info = SHOPS_DB[shop_target]
    initial_stock = shop_info['stock']
    remaining_stock = initial_stock - sold_count
    
    # 儀表板
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 設定庫存", initial_stock)
    c2.metric("💰 已售出", sold_count)
    c3.metric("🔥 剩餘數量", remaining_stock, delta_color="inverse")
    
    st.divider()
    st.subheader("📋 訂單列表")
    if not shop_orders.empty:
        st.dataframe(shop_orders, use_container_width=True)
    else:
        st.info("尚無訂單")

    if st.button("回首頁"):
        st.query_params.clear()
        st.rerun()

# ------------------------------------------
# 🟠 模式 B: 消費者 + 管理員 (預設)
# ------------------------------------------
else:
    # --- 側邊欄 ---
    with st.sidebar:
        st.header("🔒 管理員登入")
        password = st.text_input("密碼", type="password")
        
        if password == "ykk8880820":
            st.success("✅ 已登入")
            st.divider()
            
            # === 管理員專屬：店家 QR Code 列表 ===
            st.subheader("📱 商家 QR Code 列表")
            st.caption("以下是 Google Sheet 中所有店家的固定連結：")
            
            # 讓管理員輸入或確認網址 (避免預設錯誤)
            app_url = st.text_input("APP 網址", value=BASE_APP_URL)
            
            # 列出所有店家
            shop_list = list(SHOPS_DB.keys())
            selected_qr_shop = st.selectbox("預覽特定店家 QR Code", shop_list)
            
            if selected_qr_shop:
                link = f"{app_url}/?mode=shop&name={urllib.parse.quote(selected_qr_shop)}"
                qr_img = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(link)}"
                
                st.image(qr_img, caption=f"{selected_qr_shop}")
                st.code(link)
                st.info("👆 這是固定網址，只要店名不改，這個碼永久有效。")

            if st.button("清除快取 (資料更新用)"):
                st.cache_data.clear()
                st.rerun()

    # --- 主畫面 ---
    st.title("🍱 餓不死地圖")
    
    # 地圖
    st.map(MAP_DATA, zoom=13, use_container_width=True)
    
    st.divider()
    
    c1, c2 = st.columns([1, 1.5])
    
    with c1:
        st.subheader("💰 下單區")
        # 動態讀取店家選單
        target_shop = st.selectbox("選擇店家", list(SHOPS_DB.keys()))
        
        if target_shop:
            info = SHOPS_DB[target_shop]
            st.info(f"📍 {target_shop}\n\n🍱 {info['item']} | 💲 ${info['price']} | 📦 總量 {info['stock']}")
            
            u_name = st.text_input("您的暱稱")
            if st.button("🚀 搶購", type="primary", use_container_width=True):
                if not u_name:
                    st.warning("請輸入名字")
                else:
                    with st.spinner("處理中..."):
                        try:
                            full_item = f"{target_shop} - {info['item']}"
                            payload = {'user': u_name, 'item': full_item}
                            requests.post(GAS_URL, json=payload)
                            st.balloons()
                            st.success("下單成功！")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(str(e))

    with c2:
        st.subheader("📋 即時名單")
        data = get_orders()
        if data:
            df = pd.DataFrame(data)
            # 管理員刪除功能
            if password == "ykk8880820":
                st.write("🛠️ **管理員刪單**")
                options = [f"{i}: {r.get('user','?')} - {r.get('item','?')}" for i, r in df.iterrows()]
                target_del = st.selectbox("選擇刪除", options)
                if st.button("🗑️ 確認刪除"):
                    idx = int(target_del.split(":")[0])
                    delete_order(idx)
                    st.success("已刪除")
                    st.cache_data.clear()
                    st.rerun()
                st.dataframe(df, use_container_width=True)
            else:
                # 一般人看簡略版
                cols = [c for c in df.columns if c in ['時間', 'user', 'item', '姓名', '領取項目']]
                st.dataframe(df[cols].tail(10), use_container_width=True)
        else:
            st.info("暫無訂單")
