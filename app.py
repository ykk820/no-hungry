import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# ==========================================
# 1. 設定區
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbzDc3IWg8zOPfqlxm-T2zLvr7aEH3scjpr68hF878wLBNl_E8UuCeAqMPPCM75gMwf5kA/exec"
SHEET_NAME = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"

# 模擬店家資料 (之後可以進階改成從 Google Sheet 讀取)
SHOPS_DATA = pd.DataFrame({
    'shop_name': ['7-11 公園店 (剩食:3)', '全家 復興店 (剩食:5)', '路易莎 大安店 (剩食:2)', '健康餐盒 (剩食:8)'],
    'lat': [25.0330, 25.0400, 25.0350, 25.0380], 
    'lon': [121.5654, 121.5500, 121.5400, 121.5600],
    'discount_item': ['御飯糰', '友善食光麵包', '當日甜點', '水煮嫩雞便當'],
    'price': [15, 25, 40, 60]
})

# ==========================================
# 2. Google Sheet 連線函式 (包含讀取與刪除)
# ==========================================
def get_sheet_object():
    """取得 Google Sheet 物件，方便後續操作"""
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.openall()[0].worksheet(SHEET_NAME)
        return sheet
    except Exception:
        return None

def get_data():
    """讀取資料"""
    sheet = get_sheet_object()
    if sheet:
        return sheet.get_all_records()
    return []

def delete_order(row_index):
    """刪除指定行 (管理員用)"""
    sheet = get_sheet_object()
    if sheet:
        # Google Sheet 的行數是從 1 開始，且第 1 列是標題
        # 資料是從第 2 列開始
        # Pandas index 0 對應到 Sheet 的第 2 列
        sheet.delete_rows(row_index + 2)
        return True
    return False

# ==========================================
# 3. 網頁介面開始
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🗺️", layout="wide")

# --- 側邊欄：管理員登入 ---
with st.sidebar:
    st.title("🔧 系統選單")
    st.info("地圖模式：尋找最近的剩食優惠。")
    
    st.divider()
    st.header("🔒 管理員後台")
    password = st.text_input("輸入密碼", type="password")
    is_admin = False
    
    if password == "ykk8880820":
        is_admin = True
        st.success("✅ 管理員身分：可編輯刪除")
        
        # 管理員專屬按鈕
        if st.button("🔄 強制刷新資料"):
            st.cache_data.clear()
            st.rerun()

# --- 主畫面 ---
st.title("🍱 餓不死地圖 (No Hungry Map)")

# 1. 地圖區
st.subheader("📍 附近優惠店家")
st.map(SHOPS_DATA, zoom=14, use_container_width=True)

# 2. 互動區 (左邊下單，右邊管理/查看)
st.divider()
col1, col2 = st.columns([1, 1.5])

# --- 左邊：下單區 ---
with col1:
    st.subheader("💰 選擇店家搶購")
    
    selected_shop_name = st.selectbox("請選擇店家", SHOPS_DATA['shop_name'])
    selected_row = SHOPS_DATA[SHOPS_DATA['shop_name'] == selected_shop_name].iloc[0]
    item_info = f"{selected_row['discount_item']} - 特價 ${selected_row['price']}"
    st.info(f"🎯 {item_info}")
    
    # 輸入名稱
    input_label = "測試者名字 (管理員)" if is_admin else "您的暱稱"
    user_name = st.text_input(input_label, placeholder="例如: Ykk", key="user_name_input")

    if st.button("🚀 鎖定優惠 (下單)", type="primary", use_container_width=True):
        if not user_name:
            st.warning("請輸入暱稱！")
        else:
            with st.spinner("連線確認庫存中..."):
                try:
                    final_item_name = f"{selected_shop_name} - {selected_row['discount_item']}"
                    payload = {'user': user_name, 'item': final_item_name}
                    response = requests.post(GAS_URL, json=payload)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("result") == "success":
                            st.balloons()
                            st.success(f"✅ 成功！\n\n{result.get('message')}")
                            # 成功後自動刷新右邊名單
                            st.cache_data.clear() 
                        else:
                            st.error(f"⛔ {result.get('message')}")
                    else:
                        st.error("連線失敗")
                except Exception as e:
                    st.error(f"錯誤: {e}")

# --- 右邊：訂單管理/查看區 ---
with col2:
    # 讀取最新資料
    data = get_data()
    
    if data:
        df = pd.DataFrame(data)
        
        # -------------------------------
        # 管理員模式：可以刪除資料
        # -------------------------------
        if is_admin:
            st.subheader("🛠️ 訂單管理 (管理員模式)")
            
            # 顯示帶有索引的表格
            st.dataframe(df, use_container_width=True)
            st.caption("👆 上表 index 為行號 (從 0 開始)")
            
            # 刪除功能區塊
            with st.form("delete_form"):
                col_del_1, col_del_2 = st.columns([2, 1])
                with col_del_1:
                    # 讓管理員選擇要刪除哪一行 (使用 Selectbox 防止輸入錯誤)
                    # 建立一個選項列表，格式為 "index: 姓名 - 項目"
                    options = [f"{i}: {row['姓名'] if '姓名' in row else row.get('user', '未知')} - {row['領取項目'] if '領取項目' in row else row.get('item', '未知')}" for i, row in df.iterrows()]
                    delete_target = st.selectbox("選擇要刪除的訂單", options)
                
                with col_del_2:
                    st.write("") # 排版用空行
                    st.write("") 
                    delete_btn = st.form_submit_button("🗑️ 刪除此單", type="primary")
                
                if delete_btn:
                    # 從字串中解析出 index (取冒號前面的數字)
                    row_idx_to_delete = int(delete_target.split(":")[0])
                    
                    with st.spinner("刪除中..."):
                        if delete_order(row_idx_to_delete):
                            st.success(f"已刪除第 {row_idx_to_delete} 筆資料")
                            st.cache_data.clear()
                            st.rerun() # 刷新頁面
                        else:
                            st.error("刪除失敗，請檢查連線")

        # -------------------------------
        # 一般使用者模式：唯讀
        # -------------------------------
        else:
            st.subheader("📋 即時搶購名單")
            # 只顯示重要的欄位
            display_cols = [c for c in df.columns if c in ['時間', '姓名', 'user', 'User', '領取項目', 'item', 'Item', '狀態']]
            if display_cols:
                st.dataframe(df[display_cols].tail(10), use_container_width=True)
            else:
                st.dataframe(df.tail(10), use_container_width=True)
            st.caption("僅顯示最近 10 筆，登入管理員可管理所有訂單。")
            
    else:
        st.info("目前尚無資料，或無法讀取 Google Sheet。")
