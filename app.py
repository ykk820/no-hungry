import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import time
import uuid
from datetime import datetime, timedelta

# --- 1. 系統配置 ---
st.set_page_config(page_title="餓不死系統", page_icon="🍱", layout="wide")

# --- 2. 全域資料庫 ---
@st.cache_resource
def get_database():
    return {
        "shops": {},       
        "inventory": [],   
        "users": {},       
        "last_check_date": datetime.now().date() 
    }

db = get_database()

# --- 3. 自動化模組 (3AM 重置) ---
def auto_reset_daily():
    now = datetime.now()
    today_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now > today_3am and db["last_check_date"] < now.date():
        db["inventory"] = [] 
        db["last_check_date"] = now.date()

auto_reset_daily()

# --- 4. 工具模組 ---
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

# [地圖座標輔助] 淡江周邊熱點預設值
TKU_LOCATIONS = {
    "大學城 (Hi-City)": {"lat": 25.1765, "lon": 121.4425},
    "水源街 (圖書館側)": {"lat": 25.1735, "lon": 121.4440},
    "大田寮 (操場側)": {"lat": 25.1710, "lon": 121.4460},
    "捷運站周邊": {"lat": 25.1678, "lon": 121.4456},
    "其他 (自訂座標)": {"lat": 25.1750, "lon": 121.4430}
}

# --- 5. 介面模組 (View) ---

# [A] 軍師後台
def view_admin():
    st.title("🛠️ 餓不死系統 - 總指揮中心")
    st.success("🔓 管理員連線中")
    
    with st.expander("➕ 新增合作店家 (含地圖定位)", expanded=False):
        with st.form("add_shop"):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("店家名稱")
            
            # 新功能：選擇區域自動帶入座標
            location_zone = c2.selectbox("所在區域", list(TKU_LOCATIONS.keys()))
            
            # 預設座標
            default_lat = TKU_LOCATIONS[location_zone]["lat"]
            default_lon = TKU_LOCATIONS[location_zone]["lon"]
            
            c3, c4 = st.columns(2)
            # Google Maps 連結 (讓老闆自己去複製，或者你幫他查)
            map_url = c3.text_input("Google Maps 連結", placeholder="https://maps.app.goo.gl/...")
            
            # 隱藏的座標設定 (進階用，預設隱藏，需要可打開)
            # 這裡為了簡化，直接用變數存，不顯示給使用者改，除非選「其他」
            
            if st.form_submit_button("建立"):
                if new_name:
                    new_id = str(uuid.uuid4())[:8]
                    new_key = str(uuid.uuid4())
                    db["shops"][new_id] = {
                        "name": new_name, 
                        "key": new_key,
                        "location": location_zone,
                        "map_url": map_url if map_url else f"https://www.google.com/maps/search/?api=1&query={new_name}+淡江大學", # 如果沒填，自動生成搜尋連結
                        "lat": default_lat,
                        "lon": default_lon
                    }
                    st.success(f"✅ {new_name} 建立成功！已定位於：{location_zone}")
                    time.sleep(0.5)
                    st.rerun()

    st.divider()

    if not db["shops"]:
        st.warning("⚠️ 目前無店家資料。")
    else:
        st.markdown("### 📋 店家列表")
        for s_id, info in db["shops"].items():
            with st.container(border=True):
                col_a, col_b, col_c = st.columns([1, 2, 1])
                shop_url = f"?shop_key={info['key']}"
                
                with col_a:
                    st.image(generate_qr_code(shop_url), width=100)
                with col_b:
                    st.subheader(info['name'])
                    st.caption(f"📍 {info['location']}")
                    # 測試連結有效性
                    st.link_button("🗺️ Google Map", info['map_url'])
                with col_c:
                    if st.button("進入店家模式 ➜", key=f"enter_{s_id}"):
                        st.session_state.is_admin_testing = True
                        st.query_params.shop_key = info['key']
                        st.rerun()

    st.divider()
    if st.button("進入學生地圖模式 ➜", type="primary"):
        st.session_state.is_admin_testing = True
        st.session_state.force_student_view = True
        st.rerun()

# [B] 店家端
def view_shop(shop_id):
    if shop_id not in db["shops"]:
        st.error("無效的連結。")
        if st.button("回首頁"): st.query_params.clear(); st.rerun()
        return

    shop_info = db["shops"][shop_id]
    
    # 計算庫存與狀態
    my_items = [x for x in db["inventory"] if x['shop_id'] == shop_id]
    total_qty = sum([x['qty'] for x in my_items])
    is_open = total_qty > 0

    # 頂部導航
    c_title, c_btn = st.columns([3, 1])
    with c_title:
        st.title(f"👨‍🍳 {shop_info['name']}")
    with c_btn:
        if st.session_state.get("is_admin_testing"):
            if st.button("⬅️ 回後台", type="primary"):
                st.session_state.is_admin_testing = False
                st.query_params.clear()
                st.rerun()
        else:
            if st.button("登出"):
                st.query_params.clear()
                st.rerun()

    # 狀態看板
    st.divider()
    col_status, col_action = st.columns([2, 1])
    
    with col_status:
        if is_open:
            st.success(f"🟢 **營業中** (架上剩 {total_qty} 份)")
        else:
            st.info("⚫ **已打烊**")
            
    with col_action:
        if is_open:
            if st.button("🌙 我要打烊", type="primary", use_container_width=True):
                db["inventory"] = [x for x in db["inventory"] if x['shop_id'] != shop_id]
                st.toast("已打烊！", icon="🌙")
                time.sleep(1)
                st.rerun()

    st.divider()
    
    # 上架表單
    st.subheader("🚀 快速上架")
    with st.container(border=True):
        with st.form("add_item_form", clear_on_submit=True):
            f1, f2 = st.columns(2)
            item_name = f1.text_input("品項", placeholder="如: 雞腿飯")
            item_price = f2.number_input("價格", min_value=0, value=60, step=5)
            item_qty = st.number_input("數量", min_value=1, value=5)
            item_desc = st.text_input("備註", placeholder="如: 無附湯")
            
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
                    db["inventory"].append(new_item)
                    st.success(f"✅ {item_name} 上架成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("請輸入名稱")

    # 商品管理
    if my_items:
        st.subheader("📋 架上商品")
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

# [C] 學生端 (新增地圖模組)
def view_student():
    if st.session_state.get("is_admin_testing") and st.session_state.get("force_student_view"):
        if st.button("⬅️ 結束測試 (回後台)", type="primary"):
            st.session_state.is_admin_testing = False
            st.session_state.force_student_view = False
            st.rerun()
            
    st.title("🍱 餓不死地圖")
    
    if not db["shops"]:
        st.info("🚧 系統等待管理員建置中...")
        return

    # --- 側邊欄登入 ---
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

    # --- 1. 戰情地圖 (新功能) ---
    # 邏輯：找出所有「有庫存」的店家，顯示在地圖上
    active_shops_data = []
    
    # 找出有庫存的商品
    active_items = [x for x in db["inventory"] if x['qty'] > 0]
    
    # 取得這些商品所屬的店家 ID (去重)
    active_shop_ids = list(set([x['shop_id'] for x in active_items]))
    
    for s_id in active_shop_ids:
        shop = db["shops"].get(s_id)
        if shop:
            # 計算這家店剩多少
            shop_total_qty = sum([x['qty'] for x in active_items if x['shop_id'] == s_id])
            active_shops_data.append({
                "lat": shop["lat"],
                "lon": shop["lon"],
                "size": shop_total_qty * 50, # 剩越多，點越大 (視覺效果)
                "color": "#FF4B4B", # 紅色警戒色
            })
    
    # 如果有活躍店家，顯示地圖
    if active_shops_data:
        st.subheader("🗺️ 剩食戰情室")
        st.caption("紅點越大，剩食越多！")
        map_df = pd.DataFrame(active_shops_data)
        st.map(map_df, latitude="lat", longitude="lon", size="size", color="color", zoom=15)
    else:
        st.info("😴 現在地圖上一片祥和 (都沒吃的)...")

    # --- 2. 列表搶購 ---
    st.divider()
    st.subheader("🔥 正在出清")
    
    if not active_items:
        st.write("目前沒有店家營業。")
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
            c1.write(f"🍱 **{item['item']}** (${item['price']})")
            c1.caption(f"📍 {shop['location']} | {item['time']} 上架")
            
            # Google Map 導航按鈕
            c1.link_button("📍 帶我去 (Google Map)", shop['map_url'])

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

# --- 6. 路由與權限 ---
params = st.query_params
shop_key = params.get("shop_key", None)
target_shop = None

if shop_key:
    for s_id, info in db["shops"].items():
        if info['key'] == shop_key:
            target_shop = s_id

is_testing_student = st.session_state.get("force_student_view", False)

if target_shop:
    view_shop(target_shop)
elif is_testing_student:
    view_student()
else:
    current_view = "student"
    with st.sidebar:
        st.divider()
        with st.expander("🔧 系統管理"):
            pwd = st.text_input("密碼", type="password")
            if pwd == "ykk8880820":
                st.success("驗證成功")
                if st.button("進入指揮中心", type="primary"):
                    st.session_state.is_admin_logged_in = True
                    st.rerun()
    
    if st.session_state.get("is_admin_logged_in"):
        view_admin()
    else:
        view_student()
