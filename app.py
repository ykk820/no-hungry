import streamlit as st
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 設定區 (已幫你填好剛剛的網址)
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbwBSR9AjURmytbz9MTRYw3rlfzY1TMs_Uni1yQ5tDxExVHiEih8X4EI8SbYCmIb8GV1yQ/exec"
SHEET_NAME = "工作表1" # 請確認你的 Google Sheet 分頁名稱是這個

# ==========================================
# 2. 連線 Google Sheet (讀取資料用)
# ==========================================
def get_google_sheet_data():
    try:
        # 從 Streamlit Secrets 拿鑰匙
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 開啟試算表 (這裡用 project_id 對應的預設檔案，或是你可以指定網址)
        # 為了保險起見，我們抓這把鑰匙能看到的第一張表
        sheet = client.openall()[0].worksheet(SHEET_NAME)
        return sheet.get_all_records()
    except Exception as e:
        return []

# ==========================================
# 3. 網頁介面 (UI)
# ==========================================
st.title("🍙 餓不死地圖 (雲端搶購版)")

# 輸入名字
name = st.text_input("請輸入你的名字", placeholder="例如: Ykk")

# 搶購按鈕
if st.button("🚀 立即搶購", use_container_width=True):
    if not name:
        st.error("❌ 請先輸入名字！")
    else:
        with st.spinner("連線中..."):
            try:
                # 發送請求給 Google Apps Script
                headers = {'Content-Type': 'application/json'}
                payload = {'user': name, 'item': '愛心便當'}
                
                response = requests.post(GAS_URL, json=payload)
                
                # 解析回傳結果
             # 解析回傳結果
                if response.status_code == 200:
                    result = response.json() # 解析 JSON
