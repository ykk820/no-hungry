import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import time
import uuid

# --- 1. 系統配置 ---
st.set_page_config(page_title="餓不死系統", page_icon="🍱", layout="wide")

# 初始化資料庫
if 'shops' not in st.session_state:
    st.session_state.shops = {
        "u1": {"name": "大學城阿姨便當", "key": str(uuid.uuid4()), "school": "淡江大學"},
        "u2": {"name": "水源街滷味", "key": str(uuid.uuid4()), "school": "淡江大學"}
    }
if 'inventory' not in st.session_state:
    st.session_state.inventory = [
        {"shop_id": "u1", "item": "豪華剩食餐盒", "price": 60, "qty": 5, "status": "還有", "desc": "內含雞腿或排骨"},
        {"shop_id": "u2", "item": "收攤大補帖", "price": 50, "qty": 3, "status": "還有", "desc": "綜合滷味包"},
    ]
if 'users' not in st.session_state:
    st.session_state.users = {
        "bad_guy@gmail.com": {"missed": 2, "banned": False, "last_buy_time": {}}
    }

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
    st.info("請使用手機掃描下方的 QR Code 進入店家模式")
    
    for s_id, info in st.session_state.shops.items():
        col_a, col_b = st.columns([1, 3])
        # 這裡的網址要改成你實際上線後的網址
        # 暫時使用相對路徑 ?shop_key=...
        shop_url = f"?shop_key={info['key']}" 
        
        with col_a:
            st.image(generate_qr_code(shop_url), width=150)
        with col_b:
            st.subheader(info['name'])
            st.code(shop_url)
            st.caption("測試方法：複製上方 ?shop_key=... 接在網址後面")

# [B] 店家端
def view_shop(shop_id):
    shop_info = st.session_state.shops[shop_id]
    st.title(f"👨‍🍳 {shop_info['name']} - 快速上架")
    my_items = [x for x in st.session_state.inventory if x['shop_id'] == shop_id]
    for item in my_items:
        with st.container(border=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader(f"🍱 {item['item']}")
                st.write(f"${item['price']}")
            with c2:
                st.metric("庫存", f"{item['qty']}")
            b1, b2 = st.columns(2)
            if b1.button("🚀 上架+5", key=f"up_{shop_id}"):
                item['qty'] += 5
                st.rerun()
            if b2.button("🛑 完售", key=f"down_{shop_id}"):
                item['qty'] = 0
                st.rerun()

# [C] 學生端
def view_student():
    st.title("🍱 餓不死地圖")
    
    with st.sidebar:
        email = st.text_input("輸入 Gmail 登入", "test@gmail.com")
        
        if email not in st.session_state.users:
            st.session_state.users[email] = {"missed": 0, "banned": False, "last_buy_time": {}}
        
        user = st.session_state.users[email]
        if not isinstance(user.get('last_buy_time'), dict): user['last_buy_time'] = {}

        if user['banned']:
            st.error("⛔ 帳號已被封鎖")
            st.stop()
        
        st.success(f"歡迎, {email}")
        st.caption("💡 規則：同一家店 10分鐘內 限購一份")

    st.subheader("🔥 正在出清")
    for item in st.session_state.inventory:
        shop = st.session_state.shops[item['shop_id']]
        last_shop_buy = user['last_buy_time'].get(item['shop_id'], 0)
        is_cooldown = (time.time() - last_shop_buy) < 600
        
        if item['qty'] > 0:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"### {shop['name']}")
                c1.write(f"🍱 **{item['item']}** (${item['price']})")
                if is_cooldown:
                    wait_min = int(600 - (time.time() - last_shop_buy)) // 60
                    c1.warning(f"⏳ 冷卻中 ({wait_min + 1}m)")

                c2.metric("剩餘", item['qty'])
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
        else:
            st.caption(f"{shop['name']} - 已售完")

# --- 3. 路由控制 ---
params = st.query_params
shop_key = params.get("shop_key", None)
target_shop = None
if shop_key:
    for s_id, info in st.session_state.shops.items():
        if info['key'] == shop_key:
            target_shop = s_id

# --- 4. 權限管理 (隱藏後台) ---
current_view = "student"

with st.sidebar:
    st.divider()
    # 這裡就是你要的專屬密碼
    with st.expander("🔧 系統管理 (Admin Only)"):
        admin_pwd = st.text_input("輸入管理密碼", type="password")
        
        # 修改點：密碼已更新為 ykk8880820
        if admin_pwd == "ykk8880820":  
            st.success("身分驗證成功")
            current_view = "admin"
        elif admin_pwd:
            st.error("密碼錯誤")

# --- 5. 最終畫面呈現 ---
if target_shop:
    view_shop(target_shop)
elif current_view == "admin":
    view_admin()
else:
    view_student()
