import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# ==========================================
# 1. 設定區 (請確認這裡的網址是對的)
# ==========================================
# 你的 Google Apps Script 網址
GAS_URL = "https://script.google.com/macros/s/AKfycbzDc3IWg8zOPfqlxm-T2zLvr7aEH3scjpr68hF878wLBNl_E8UuCeAqMPPCM75gMwf5kA/exec"
# 你的 Google Sheet 分頁名稱
SHEET_NAME = "1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw" 

# ==========================================
# 2. 核心功能：讀取 Google Sheet
# ==========================================
def get_data():
    """從 Google Sheet 讀取目前的排隊名單"""
    try:
        if "gcp_service_account" not in st.secrets:
            return None
            
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 讀取資料
        sheet = client.openall()[0].worksheet(SHEET_NAME)
        data = sheet.get_all_records()
        return data
    except Exception as e:
        return []

# ==========================================
# 3. 網頁介面開始
# ==========================================
st.set_page_config(page_title="剩食優惠地圖", page_icon="🍱", layout="wide")

# --- 側邊欄：管理員登入 ---
with st.sidebar:
    st.header("🔒 管理員專區")
    password = st.text_input("輸入管理員密碼", type="password")
    
    is_admin = False
    if password == "ykk8880820":
        st.success("✅ 管理員身分已驗證")
        is_admin = True
        if st.button("🔄 強制刷新資料"):
            st.cache_data.clear()
            st.rerun()
    elif password:
        st.error("❌ 密碼錯誤")

# --- 主畫面：標題 ---
st.title("🍱 剩食優惠地圖")
st.markdown("### 🌍 惜食不浪費，美味便宜帶回家")
st.info("📢 目前規則：每人 10 分鐘內只能搶購一次，請把握機會！")

# 畫面切分：左邊搶購，右邊看排隊
col1, col2 = st.columns([1, 1.5])

# --- 左邊：搶購區 ---
with col1:
    st.subheader("💰 限時優惠搶購")
    
    # 讓使用者選擇要搶什麼 (或是你可以改成固定項目)
    item_option = st.selectbox(
        "選擇優惠餐點", 
        ["日式便當 (原價$120 / 特價$60)", "歐式麵包組 (原價$80 / 特價$30)", "生鮮蔬果包 (原價$150 / 特價$50)"]
    )
    
    # 如果是管理員，可以自己輸入名字測試；如果是路人，就輸入自己的名字
    user_input_label = "輸入您的暱稱"
    if is_admin:
        user_input_label = "輸入測試者名稱 (管理員模式)"
        
    name = st.text_input(user_input_label, placeholder="例如: Ykk")

    if st.button("🚀 立即下單", use_container_width=True, type="primary"):
        if not name:
            st.warning("請先輸入名字！")
        else:
            with st.spinner("連線確認庫存中..."):
                try:
                    # 傳送資料給 Google Sheet
                    payload = {'user': name, 'item': item_option}
                    response = requests.post(GAS_URL, json=payload)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("result") == "success":
                            st.balloons()
                            st.success(f"🎉 搶購成功！\n\n{result.get('message')}")
                        else:
                            st.error(f"⛔ {result.get('message')}") # 顯示10分鐘限制訊息
                    else:
                        st.error(f"連線失敗 ({response.status_code})")
                except Exception as e:
                    st.error(f"系統錯誤: {str(e)}")

# --- 右邊：即時排隊名單 ---
with col2:
    st.subheader("📋 目前排隊/搶購名單")
    
    # 讀取資料
    data = get_data()
    
    if data:
        df = pd.DataFrame(data)
        
        # 簡單美化一下表格
        if not df.empty:
            # 如果是管理員，顯示所有資料
            if is_admin:
                st.dataframe(df, use_container_width=True)
                st.caption("👀 管理員可見完整詳細資料")
            else:
                # 如果是一般人，只顯示最近 5 筆，且隱藏敏感資訊(如果有)
                # 這裡我們顯示 時間、姓名、項目
                display_cols = [col for col in df.columns if col in ['時間', '姓名', 'User', 'user', 'Item', 'item', '領取項目', '項目']]
                if display_cols:
                    st.dataframe(df[display_cols].tail(10), use_container_width=True)
                else:
                    st.dataframe(df.tail(10), use_container_width=True)
                st.caption("僅顯示最近 10 筆搶購紀錄")
    else:
        st.info("目前還沒有人搶購，快來當第一個！")

# --- 底部版權 ---
st.divider()
st.caption("No Hungry Map Project © 2025")
