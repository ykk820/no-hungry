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
    # last_buy_time 改成字典格式：{'shop_id': timestamp}
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

# [A] 軍師後台
def view_admin():
    st.title("🛠️ 餓不死系統 - 總指揮中心")
    st.info("請使用手機掃描下方的 QR Code 進入店家模式")
    for s_id, info in st.session_state.shops.items():
        col_a, col_b = st.columns([1, 3])
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
    
    # 登入邏輯
    with st.sidebar:
        email = st.text_input("輸入 Gmail 登入", "test@gmail.com")
        
        if email not in st.session_state.users:
            # 初始化：注意 last_buy_time 是一個空字典 {}
            st.session_state.users[email] = {"missed": 0, "banned": False, "last_buy_time": {}}
        
        user = st.session_state.users[email]
        
        # 確保舊資料格式相容 (防止報錯)
        if not isinstance(user.get('last_buy_time'), dict):
            user['last_buy_time'] = {}

        if user['banned']:
            st.error("⛔ 帳號已被封鎖")
            st.stop()
        
        st.success(f"歡迎, {email}")
        st.caption("💡 規則：同一家店 10分鐘內 限購一份，但可以去搶別家！")

    st.subheader("🔥 正在出清")
    for item in st.session_state.inventory:
        shop = st.session_state.shops[item['shop_id']]
        
        # 計算該使用者對「這家店」的冷卻狀態
        last_shop_buy = user['last_buy_time'].get(item['shop_id'], 0)
        is_cooldown = (time.time() - last_shop_buy) < 600
        
        if item['qty'] > 0:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                
                # 顯示商品資訊
                c1.markdown(f"### {shop['name']}")
                c1.write(f"🍱 **{item['item']}** (${item['price']})")
                if is_cooldown:
                    wait_min = int(600 - (time.time() - last_shop_buy)) // 60
                    c1.warning(f"⏳ 這家店還要等 {wait_min + 1} 分鐘才能再買")

                c2.metric("剩餘", item['qty'])
                
                # 按鈕邏輯
                # 如果在冷卻中，按鈕文字會變，雖然可以按，但會被擋
                btn_label = "我要搶" if not is_cooldown else "🚫 休息中"
                
                if c2.button(btn_label, key=f"buy_{item['shop_id']}"):
                    # 1. 檢查：這家店是否在 CD 中？
                    if is_cooldown:
                         st.toast(f"❌ {shop['name']} 你剛買過，留給別人吧！去看看別家。", icon="🚫")
                    else:
                        # 2. 通過：扣庫存
                        item['qty'] -= 1
                        # 3. 紀錄：更新這家店的購買時間
                        user['last_buy_time'][item['shop_id']] = time.time()
                        
                        st.balloons()
                        st.success(f"✅ 成功搶到 {shop['name']}！")
                        time.sleep(1)
                        st.rerun()
        else:
            st.caption(f"{shop['name']} - 已售完")

# --- 3. 路由 ---
params = st.query_params
shop_key = params.get("shop_key", None)
target_shop = None
if shop_key:
    for s_id, info in st.session_state.shops.items():
        if info['key'] == shop_key:
            target_shop = s_id

with st.sidebar:
    st.divider()
    mode = st.radio("切換視角", ["學生端", "軍師後台"])

if target_shop:
    view_shop(target_shop)
elif mode == "軍師後台":
    view_admin()
else:
    view_student()
