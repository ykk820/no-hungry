import streamlit as st
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 設定區 (你的 GAS 網址)
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbwBSR9AjURmytbz9MTRYw3rlfzY1TMs_Uni1yQ5tDxExVHiEih8X4EI8SbYCmIb8GV1yQ/exec"

# ==========================================
# 2. 讀取 Google Sheet 資料 (容錯版)
#    如果金鑰沒設好，這裡會跳過，不會讓整個網頁掛掉
# ==========================================
def get_google_sheet_data():
    try:
        # 嘗試從 Streamlit Secrets 拿金鑰
        if "gcp_service_account" not in st.secrets:
            return None # 沒有設定金鑰，直接回傳空
            
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 開啟第一張試算表
        sheet = client.openall()[0].get_worksheet(0) 
        return sheet.get_all_records()
    except Exception as e:
        print(f"讀取失敗: {e}")
        return None

# ==========================================
# 3. 網頁介面 (UI)
# ==========================================
st.title("🍱 餓不死地圖 (搶購測試)")

# 輸入名字
name = st.text_input("請輸入你的名字", placeholder="例如: Ykk")

# --------------------------------
# 搶購按鈕區塊
# --------------------------------
if st.button("🚀 立即搶購", use_container_width=True):
    if not name:
        st.error("❌ 請先輸入名字！")
    else:
        with st.spinner("連線處理中..."):
            try:
                # 準備資料
                payload = {'user': name, 'item': '愛心便當'}
                
                # 發送請求給 Google Apps Script
                response = requests.post(GAS_URL, json=payload)
                
                # 判斷結果
                if response.status_code == 200:
                    result = response.json()
                    
                    if result.get("result") == "success":
                        st.balloons() # 成功撒花
                        st.success(f"✅ {result.get('message')}")
                    else:
                        st.error(f"⚠️ {result.get('message')}")
                else:
                    st.error(f"連線失敗 (狀態碼: {response.status_code})")
            
            except Exception as e:
                st.error(f"程式發生錯誤: {str(e)}")

# --------------------------------
# 顯示名單區塊
# --------------------------------
st.divider()
st.subheader("📋 目前搶購名單")

if st.button("🔄 刷新名單"):
    st.rerun()

# 讀取資料
df = get_google_sheet_data()

if df:
    st.dataframe(df, use_container_width=True)
else:
    st.info("目前無法讀取名單 (可能是還沒設定 Secrets 金鑰)，但上面的「搶購功能」依然可以用喔！")
