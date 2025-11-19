import streamlit as st
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 設定區
# ==========================================
# 請填入第一階段拿到的 GAS 網址
GAS_URL = "https://script.google.com/macros/s/AKfycbzDc3IWg8zOPfqlxm-T2zLvr7aEH3scjpr68hF878wLBNl_E8UuCeAqMPPCM75gMwf5kA/exec" 

# 請填入 Google Sheet 的分頁名稱
SHEET_NAME = ="1H69bfNsh0jf4SdRdiilUOsy7dH6S_cde4Dr_5Wii7Dw"

# ==========================================
# 功能函式
# ==========================================
def get_data():
    """從 Google Sheet 讀取領取名單"""
    try:
        if "gcp_service_account" not in st.secrets:
            return None
            
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 抓取第一張報表中的指定分頁
        sheet = client.openall()[0].worksheet(SHEET_NAME)
        return sheet.get_all_records()
    except Exception as e:
        return []

# ==========================================
# 網頁介面
# ==========================================
st.set_page_config(page_title="餓不死地圖", page_icon="🍱")

st.title("🍱 餓不死地圖")
st.markdown("幫助有需要的人，共享資源。")

# --- 領取區塊 ---
with st.container():
    st.subheader("我要領取")
    name = st.text_input("您的稱呼", placeholder="請輸入姓名")
    
    # 按鈕
    if st.button("確認領取", type="primary", use_container_width=True):
        if not name:
            st.warning("請輸入稱呼才能領取喔！")
        else:
            with st.spinner("系統處理中..."):
                try:
                    payload = {'user': name, 'item': '待用餐一份'}
                    response = requests.post(GAS_URL, json=payload)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("result") == "success":
                            st.balloons()
                            st.success(f"✅ {result.get('message')}")
                        else:
                            st.error(f"⚠️ {result.get('message')}")
                    else:
                        st.error("連線異常，請稍後再試。")
                except Exception as e:
                    st.error("發生未知錯誤，請聯繫管理員。")

st.divider()

# --- 即時名單區塊 ---
st.subheader("📋 今日領取狀況")
if st.button("刷新名單"):
    st.rerun()

data = get_data()
if data:
    st.dataframe(data, use_container_width=True)
else:
    st.info("目前尚無領取紀錄，或系統正在同步中。")
