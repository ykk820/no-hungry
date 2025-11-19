import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import time
import uuid
from datetime import datetime

# --- 1. 系統配置 ---
st.set_page_config(page_title="餓不死系統", page_icon="🍱", layout="wide")

# --- 2. 核心：全域資料庫 (Global Database) ---
# 這是這次改版的關鍵！我們用 @st.cache_resource 把資料鎖在伺服器記憶體裡
# 這樣不管你刷新幾次，或是不同人用不同手機開，大家看到的都是「同一份」資料

@st.cache_resource
def get_database():
    # 這裡回傳一個字典，當作我們的「雲端資料庫」
    return {
        "shops": {},      # 存放店家帳號
        "inventory": [],  # 存放所有架上商品
        "users": {}       # 存放使用者紀錄
    }

# 初始化資料庫 (db 就是我們全域共用的變數)
db = get_database()

# --- 3. 工具模組 ---
def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue()

def get_time_string():
    return datetime.now().strftime("%H:%M")

# --- 4. 介面模組 ---

# [A] 軍師後台
def view_admin():
    st.title("🛠️ 餓不死系統 - 總指揮中心")
    st.success("🔓 管理員連線中 | 資料庫狀態: 連線正常")
    
    # 新增店家
    with st.expander("➕ 新增合作店家", expanded=False):
        with st.form("add_shop"):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("店家名稱")
            new_school = c2.text_input("所屬學校", value="淡江大學")
            
            if st.form_submit_button("建立檔案"):
                if new_name:
                    new_id = str(uuid.uuid4())[:8]
                    new_key = str(uuid.uuid4())
                    # 寫入全域資料庫
                    db["shops"][new_id] = {
                        "name": new_name, 
                        "key": new_key, 
                        "school": new_school
                    }
                    st.success(f"✅ {new_name} 建立成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("請輸入店名")

    st.divider()

    # 店家列表
    if not db["shops"]:
        st.warning("⚠️ 目前無店家資料。")
    else:
        st.markdown("### 📋 店家列表 (手機掃碼測試)")
        for s_id, info in db["shops"].items():
            with st.container(border=True):
                col_a, col_b, col_c = st.columns([1, 2, 1])
                # 這裡會抓取當前網頁的網址，自動串接參數
                base_url = st.experimental_get_query_params().get("base_url", [""])[0]
                # 如果是在 Streamlit Cloud，這裡可以用相對路徑
                shop_url = f"?shop_key={info['key']}"
                
                with col_a:
                    st.image(generate_qr_code(shop_url), width=100)
                with col_b:
                    st.subheader(info['name'])
                    st.code(shop_url)
                    st.caption(f"Key: {info['key'][:6]}...")
                with col_c:
                    if st.button("進入後台 ➜", key=f"enter_{s_id}"):
                        st.query_params.shop_key = info['key']
                        st.rerun()

# [B] 店家端
def view_shop(shop_id):
    if shop_id not in db["shops"]:
        st.error("無效的連結。")
        if st.button("回首頁"): st.query_params.clear(); st.rerun()
        return

    shop_info = db["shops"][shop_id]
    
    # 頂部導覽
    c_title, c_exit = st.columns([3, 1])
    with c_title:
        st.title(f"👨‍🍳 {shop_info['name']}")
    with c_exit:
        if st.button("⬅️ 登出"):
            st.query_params.clear()
            st.rerun()

    st.divider()
    
    # 上架表單
    st.subheader("🚀 快速上架")
    with st.container(border=True):
        with st.form("add_item_form", clear_on_submit=True):
            f1, f2 = st.columns(2)
            item_name = f1.text_input("品項", placeholder="例如: 雞腿飯")
            item_price = f2.number_input("價格", min_value=0, value=60, step=5)
            item_qty = st.number_input("數量", min_value=1, value=5)
            item_desc = st.text_input("備註", placeholder="例如: 無附湯")
            
            if st.form_submit_button("確認上架", use_container_width=True):
                if item_name:
                    new_item = {
                        "id": str(uuid.uuid4())[:6],
                        "shop_id": shop_id,
                        "item": item_name,
                        "price": item_price,
                        "qty": item_qty,
                        "desc": item_desc,
                        "time": get_time_string()
                    }
                    # 寫入全域資料庫
                    db["inventory"].append(new_item)
                    st.success(f"✅ {item_name} 上架成功！")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("請輸入名稱")

    # 管理架上商品
    st.subheader("📋 架上管理")
    my_items = [x for x in db["inventory"] if x['shop_id'] == shop_id]
    
    if not my_items:
        st.info("目前架上是空的。")
    else:
        if st.button("🛑 一鍵收攤 (清空)", type="primary", use_container_width=True):
            # 保留其他店家的商品，只刪除這家店的
            db["inventory"] = [x for x in db["inventory"] if x['shop_id'] != shop_id]
            st.success("已清空！")
            time.sleep(1)
            st.rerun()
            
        for item in my_items:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.write(f"**{item['item']}**")
                    st.caption(f"${item['price']} | 剩 {item['qty']}")
                with c2:
                    if st.button("➕", key=f"add_{item['id']}"):
                        item['qty'] += 1
                        st.rerun()
                with c3:
                    if st.button("🗑️", key=f"del_{item['id']}"):
                        db["inventory"].remove(item)
                        st.rerun()

# [C] 學生端
def view_student():
    st.title("🍱 餓不死地圖")
    
    # 檢查是否有店家
    if not db["shops"]:
        st.info("🚧 系統等待管理員建置中...")
        return

    # 側邊欄
    with st.sidebar:
        email = st.text_input("輸入 Gmail 登入", placeholder="ykk@gmail.com")
        
        if email:
            if email not in db["users"]:
                db["users"][email] = {"missed": 0, "banned": False, "last_buy_time": {}}
            
            user = db["users"][email]
            if not isinstance(user.get('last_buy_time'), dict): user['last_buy_time'] = {}

            if user['banned']:
                st.error("⛔ 帳號已被封鎖")
                st.stop()
            
            st.success(f"歡迎, {email}")
            st.caption("💡 規則：同一家店 10分鐘內 限購一份")
        else:
            st.warning("請先輸入 Email")

    # 商品牆
    st.subheader("🔥 正在出清")
    active_items = [x for x in db["inventory"] if x['qty'] > 0]
    
    if not active_items:
        st.info("😴 目前所有店家都休息了。")
        return

    for item in active_items:
        shop = db["shops"].get(item['shop_id'])
        if not shop: continue

        user = db["users"].get(email) if email else None
        last_shop_buy = user['last_buy_time'].get(item['shop_id'], 0) if user else 0
        is_cooldown = (time.time() - last_shop_buy) < 600
        
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            
            c1.markdown(f"### {shop['name']}")
            c1.write(f"🍱 **{item['item']}**")
            c1.write(f"💰 **${item['price']}**")
            if item['desc']: c1.caption(f"備註: {item['desc']}")
            c1.caption(f"上架: {item['time']}")

            c2.metric("剩餘", item['qty'])
            
            if email and is_cooldown:
                wait_min = int(600 - (time.time() - last_shop_buy)) // 60
                c1.warning(f"⏳ 冷卻 ({wait_min + 1}m)")

            if not email:
                c2.button("登入搶", disabled=True, key=f"dis_{item['id']}")
            else:
                btn_label = "我要搶" if not is_cooldown else "🚫 休息"
                if c2.button(btn_label, key=f"buy_{item['id']}"):
                    if is_cooldown:
                         st.toast(f"❌ {shop['name']} 冷卻中", icon="🚫")
                    else:
                        item['qty'] -= 1
                        user['last_buy_time'][item['shop_id']] = time.time()
                        st.balloons()
                        st.success("搶購成功！")
                        time.sleep(0.5)
                        st.rerun()

# --- 5. 路由與入口 ---
params = st.query_params
shop_key = params.get("shop_key", None)
target_shop = None

if shop_key:
    for s_id, info in db["shops"].items():
        if info['key'] == shop_key:
            target_shop = s_id

current_view = "student"
if not target_shop:
    with st.sidebar:
        st.divider()
        with st.expander("🔧 系統管理"):
            pwd = st.text_input("密碼", type="password")
            if pwd == "ykk8880820":
                st.success("OK")
                mode = st.radio("Mode", ["Admin", "Student"])
                if mode == "Admin": current_view = "admin"

if target_shop:
    view_shop(target_shop)
elif current_view == "admin":
    view_admin()
else:
    view_student()
