import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import urllib.parse

# ==========================================
# 1. 設定區 (已代入你的資料)
# ==========================================
# 你的 Google Apps Script 網址 (寫入資料用)
GAS_URL = "https://script.google.com/macros/s/AKfycbzDc3IWg8zOPfqlxm-T2zLvr7aEH3scjpr68hF878wLBNl_E8UuCeAqMPPCM75gMwf5kA/exec"

# 你的 Google Sheet ID (讀取/刪除資料用)
SPREADSHEET_ID = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"
SHEET_NAME = "領取紀錄" # 請確認你的分頁名稱是這個

# 模擬店家資料庫 (未來可改成從 Sheet 讀取)
SHOPS_DB = {
    '7-11 公園店': {'lat': 25.0330, 'lon': 121.5654, 'item': '御飯糰', 'price': 15, 'stock': 10},
    '全家 復興店': {'lat': 25.0400, 'lon': 121.5500, 'item': '友善食光麵包', 'price': 25, 'stock': 8},
    '路易莎 大安店': {'lat': 25.0350, 'lon': 121.5400, 'item': '當日甜點', 'price': 40, 'stock': 5},
    '健康餐盒': {'lat': 25.0380, 'lon': 121.5600, 'item': '水煮嫩雞便當', 'price': 60, 'stock': 15},
}

# 轉成 DataFrame 給地圖顯示用
MAP_DATA = pd.DataFrame([
    {'shop_name': k, 'lat': v['lat'], 'lon': v['lon']} for k, v in SHOPS_DB.items()
])

# ==========================================
# 2. 後端連線與功能函式
# ==========================================
def get_sheet_object():
    """取得 Google Sheet 物件"""
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 使用你提供的 ID 精準開啟表格
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        return sheet
    except Exception as e:
        # 如果找不到分頁或連線失敗，回傳 None
        print(f"連線錯誤: {e}")
        return None

def get_data():
    """讀取所有訂單資料"""
    sheet = get_sheet_object()
    return sheet.get_all_records() if sheet else []

def delete_order(row_index):
    """刪除指定訂單 (管理員用)"""
    sheet = get_sheet_object()
    if sheet:
        # Sheet 列數 = DataFrame index + 2 (標題佔1行, 從1開始算)
        sheet.delete_rows(row_index + 2)
        return True
    return False

# ==========================================
# 3. 頁面路由 (判斷現在是誰)
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱", layout="wide")

# 取得網址參數 (?mode=shop&name=xxx)
params = st.query_params
current_mode = params.get("mode", "consumer") 
shop_target = params.get("name", None)

# ==========================================
# 🔵 模式 A: 商家後台模式 (掃 QR Code 進入)
# ==========================================
if current_mode == "shop" and shop_target in SHOPS_DB:
    st.title(f"🏪 商家後台：{shop_target}")
    st.caption("📊 此頁面顯示您的銷售狀況與庫存")
    
    if st.button("🔄 刷新數據", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    # 1. 計算數據
    all_orders = get_data()
    df = pd.DataFrame(all_orders)
    
    # 篩選出這家店的訂單 (比對 item 名稱)
    if not df.empty:
        # 確保欄位名稱統一 (轉成字串比對)
        shop_orders = df[df.apply(lambda row: shop_target in str(row.values), axis=1)]
        sold_count = len(shop_orders)
    else:
        shop_orders = pd.DataFrame()
        sold_count = 0
        
    initial_stock = SHOPS_DB[shop_target]['stock']
    remaining_stock = initial_stock - sold_count
    
    # 2. 儀表板
    col1, col2, col3 = st.columns(3)
    col1.metric("📦 初始庫存", initial_stock)
    col2.metric("💰 已售出", sold_count)
    col3.metric("🔥 剩餘庫存", remaining_stock, delta_color="inverse")
    
    st.divider()
    
    # 3. 訂單明細
    st.subheader("📋 您的訂單明細")
    if not shop_orders.empty:
        st.dataframe(shop_orders, use_container_width=True)
    else:
        st.info("目前尚未有訂單")

    # 離開
    if st.button("⬅️ 回首頁"):
        st.query_params.clear()
        st.rerun()

# ==========================================
# 🟠 模式 B: 消費者模式 + 管理員登入 (預設)
# ==========================================
else:
    # --- 側邊欄：管理員登入 ---
    with st.sidebar:
        st.header("🔒 管理員專區")
        password = st.text_input("輸入密碼", type="password")
        is_admin = False
        
        if password == "ykk8880820":
            is_admin = True
            st.success("✅ 管理員身分驗證成功")
            
            st.divider()
            st.subheader("📱 產生商家 QR Code")
            st.info("選一個店家，產生專屬後台連結")
            qr_shop = st.selectbox("選擇店家", list(SHOPS_DB.keys()))
            
            # 自動偵測目前網址 (如果是在本地跑 localhost，上線後會變)
            # 這裡預設為你 Streamlit Cloud 的網址結構
            base_url = "https://no-hungry.streamlit.app" 
            # 💡 注意：請把上面這行換成你實際的網址，例如 https://your-app-name.streamlit.app
            
            shop_link = f"{base_url}/?mode=shop&name={urllib.parse.quote(qr_shop)}"
            
            st.code(shop_link, language="text")
            st.caption("👆 複製這個連結，或讓商家掃描下方 QR Code")
            
            # 產生 QR Code 圖片
            qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={urllib.parse.quote(shop_link)}"
            st.image(qr_api, caption=f"{qr_shop} 後台入口")
            
            st.divider()
            if st.button("🔄 強制刷新全站"):
                st.cache_data.clear()
                st.rerun()

    # --- 主畫面內容 ---
    st.title("🍱 餓不死地圖 (剩食優惠)")
    
    if is_admin:
        st.warning("🔧 管理員模式開啟：您可以刪除訂單、查看完整資料")
    
    # 1. 地圖區
    st.subheader("📍 附近優惠地圖")
    st.map(MAP_DATA, zoom=14, use_container_width=True)

    st.divider()
    
    # 2. 下單與列表區
    c1, c2 = st.columns([1, 1.5])
    
    with c1:
        st.subheader("💰 選擇店家搶購")
        target_shop = st.selectbox("請選擇", list(SHOPS_DB.keys()))
        shop_info = SHOPS_DB[target_shop]
        
        st.info(f"🎯 {shop_info['item']}\n\n💵 特價 ${shop_info['price']} (限量 {shop_info['stock']} 份)")
        
        user_input = st.text_input("您的暱稱", placeholder="例如: Ykk")
        
        if st.button("🚀 下單搶購", type="primary", use_container_width=True):
            if not user_input:
                st.warning("請輸入名字！")
            else:
                with st.spinner("連線確認中..."):
                    try:
                        # 組合：店名 - 商品
                        full_item_name = f"{target_shop} - {shop_info['item']}"
                        payload = {'user': user_input, 'item': full_item_name}
                        
                        response = requests.post(GAS_URL, json=payload)
                        if response.status_code == 200:
                            res = response.json()
                            if res.get("result") == "success":
                                st.balloons()
                                st.success(f"✅ {res.get('message')}")
                                st.cache_data.clear() # 刷新讓右邊更新
                            else:
                                st.error(f"⚠️ {res.get('message')}")
                        else:
                            st.error("連線失敗")
                    except Exception as e:
                        st.error(f"錯誤: {e}")

    with c2:
        st.subheader("📋 即時搶購名單")
        data = get_data()
        
        if data:
            df = pd.DataFrame(data)
            
            # === 管理員：刪除功能 ===
            if is_admin:
                st.write("🛠️ **訂單管理**")
                if not df.empty:
                    # 建立刪除選單
                    del_options = [f"{i}: {r.get('user', r.get('姓名','?'))} - {r.get('item', r.get('領取項目','?'))}" for i, r in df.iterrows()]
                    target_del = st.selectbox("選擇要刪除的訂單", del_options)
                    
                    if st.button("🗑️ 刪除此單"):
                        row_idx = int(target_del.split(":")[0])
                        if delete_order(row_idx):
                            st.success("已刪除！")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("刪除失敗")
                st.dataframe(df, use_container_width=True)
            
            # === 一般人：唯讀 ===
            else:
                if not df.empty:
                    # 嘗試抓取正確的欄位名稱顯示
                    cols = [c for c in df.columns if c in ['時間', '姓名', 'user', 'item', '領取項目']]
                    st.dataframe(df[cols].tail(10), use_container_width=True)
                    st.caption("顯示最近 10 筆交易")
                else:
                    st.info("尚無資料")
        else:
            st.info("目前無訂單")
