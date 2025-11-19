import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import time
import uuid

# --- 1. 系統配置 ---
st.set_page_config(page_title="餓不死系統", page_icon="🍱", layout="wide")

# --- 初始化資料庫 (全空狀態) ---
if 'shops' not in st.session_state:
    st.session_state.shops = {}  # 全空：等待管理員新增

if 'inventory' not in st.session_state:
    st.session_state.inventory = [] # 全空：等待店家上架

if 'users' not in st.session_state:
    st.session_state.users = {} # 全空：等待學生登入

# --- 2. 功能模組 ---
def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue()

# [A] 軍師後台 (隱藏版)
def view_admin():
    st.title("🛠️ 餓不死系統 - 總指揮中心")
    st.success("🔓 管理員身分驗證通過")
    
    # --- 新增店家功能 ---
    st.markdown("### ➕ 新增合作店家")
    with st.form("add_shop_form"):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("店家名稱 (例如: 大學城阿姨便當)")
        new_school = c2.text_input("所屬學校", value="淡江大學")
        
        submitted = st.form_submit_button("建立店家檔案")
        if submitted and new_name:
            # 生成唯一 ID 與 Key
            new_id = str(uuid.uuid4())[:8] 
            new_key = str(uuid.uuid4())
            
            # 存入店家資料
            st.session_state.shops[new_id] = {
                "name": new_name, 
                "key": new_key, 
                "school": new_school
            }
            
            # 自動建立一個預設商品
            st.session_state.inventory.append({
                "shop_id": new_id, 
                "item": "餓不死驚喜包", 
                "price": 60, 
                "qty": 0, 
                "status": "售完", 
                "desc": "老闆看心情裝，保證超值"
            })
            
            st.success(f"✅ 已建立：{new_name}！")
            time.sleep(1)
            st.rerun()

    st.divider()

    # --- 顯示店家列表與 QR Code ---
    if not st.session_state.shops:
        st.warning("⚠️ 目前還沒有任何店家，請在上方建立。")
    else:
        st.markdown("### 📋 店家列表 & 專屬鑰匙")
        for s_id, info in st.session_state.shops.items():
            with st.container(border=True):
                col_a, col_b = st.columns([1, 3])
                # 請注意：上線後若網址不同，這裡的參數會接在你的新網址後面
                shop_url = f"?shop_key={info['key']}" 
                
                with col_a:
                    st.image(generate_qr_code(shop_url), width=150)
                with col_b:
                    st.subheader(info['name'])
                    st.code(shop_url)
                    st.caption("將此 QR Code 截圖傳給老闆。")

# [B] 店家端
def view_shop(shop_id):
    if shop_id not in st.session_state.shops:
        st.error("店家資料不存在。")
        return

    shop_info = st.session_state.shops[shop_id]
    st.title(f"👨‍🍳 {shop_info['name']} - 快速上架")
    
    my_items = [x for x in st.session_state.inventory if x['shop_id'] == shop_id]
    
    if not my_items:
        st.info("目前沒有商品。")
    
    for item in my_items:
        with st.container(border=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader(f"🍱 {item['item']}")
                st.write(f"${item['price']} | {item['desc']}")
            with c2:
                st.metric("目前庫存", f"{item['qty']}")
            
            b1, b2 = st.columns(2)
            if b1.button("🚀 上架 +5", key=f"up_{shop_id}_{item['item']}"):
                item['qty'] += 5
                st.rerun()
            if b2.button("🛑 完售 / 歸零", key=f"down_{shop_id}_{item['item']}"):
                item['qty'] = 0
                st.rerun()

# [C] 學生端
def view_student():
    st.title("🍱 餓不死地圖")
    
    # 檢查系統是否為空
    if not st.session_state.shops:
        st.info("🚧 系統初始化中，請管理員先新增店家。")
        st.stop()

    with st.sidebar:
        # 這裡修改了：沒有預設值，placeholder 只是提示
        email = st.text_input("輸入 Gmail 登入", placeholder="例如: ykk@gmail.com")
        
        if email:
            if email not in st.session_state.users:
                st.session_state.users[email] = {"missed": 0, "banned": False, "last_buy_time": {}}
            
            user = st.session_state.users[email]
            if not isinstance(user.get('last_buy_time'), dict): user['last_buy_time'] = {}

            if user['banned']:
                st.error("⛔ 帳號已被封鎖")
                st.stop()
            
            st.success(f"歡迎, {email}")
            st.caption("💡 規則：同一家店 10分鐘內 限購一份")
        else:
            st.warning("👈 請先在左側輸入 Email")

    st.subheader("🔥 正在出清")
    
    has_food = False
    for item in st.session_state.inventory:
        shop = st.session_state.shops.get(item['shop_id'])
        if not shop: continue

        # 檢查冷卻時間
        user = st.session_state.users.get(email) if email else None
        last_shop_buy = 0
        if user:
            last_shop_buy = user['last_buy_time'].get(item['shop_id'], 0)
        
        is_cooldown = (time.time() - last_shop_buy) < 600
        
        if item['qty'] > 0:
            has_food = True
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"### {shop['name']}")
                c1.write(f"🍱 **{item['item']}** (${item['price']})")
                
                if email and is_cooldown:
                    wait_min = int(600 - (time.time() - last_shop_buy)) // 60
                    c1.warning(f"⏳ 冷卻中 ({wait_min + 1}m)")

                c2.metric("剩餘", item['qty'])
                
                if not email:
                    c2.button("請先登入", disabled=True, key=f"dis_{item['shop_id']}")
                else:
                    btn_label = "我要搶" if not is_cooldown else "🚫 休息中"
                    if c2.button(btn_label, key=f"buy_{item['shop_id']}"):
                        if is_cooldown:
                             st.toast(f"❌ {shop['name']} 還在 CD 時間！", icon="🚫")
                        else:
                            item['qty'] -= 1
                            user['last_buy_time'][item['shop_id']] = time.time()
                            st.balloons()
                            st.success(f"✅ 搶購成功！")
                            time.sleep(1)
                            st.rerun()
    
    if not has_food:
        st.info("😴 目前所有店家都還沒上架，或是都被搶光了！")

# --- 3. 路由控制 ---
params = st.query_params
shop_key = params.get("shop_key", None)
target_shop = None
if shop_key:
    for s_id, info in st.session_state.shops.items():
        if info['key'] == shop_key:
            target_shop = s_id

# --- 4. 權限管理 ---
current_view = "student"

with st.sidebar:
    st.divider()
    with st.expander("🔧 系統管理 (Admin Only)"):
        admin_pwd = st.text_input("輸入管理密碼", type="password")
        if admin_pwd == "ykk8880820":  
            st.success("身分驗證成功")
            current_view = "admin"
        elif admin_pwd:
            st.error("密碼錯誤")

# --- 5. 最終畫面 ---
if target_shop:
    view_shop(target_shop)
elif current_view == "admin":
    view_admin()
else:
    view_student()
