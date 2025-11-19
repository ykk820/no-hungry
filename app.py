import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import time
import uuid
from datetime import datetime, timedelta
import math
from streamlit_js_eval import get_geolocation

# --- 1. 系統配置 ---
st.set_page_config(page_title="餓不死系統", page_icon="🍱", layout="wide")

hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 2. 全域資料庫 ---
@st.cache_resource
def get_database():
    return {
        "shops": {},       
        "inventory": [],   
        "users": {},       
        "last_check_date": datetime.now().date(),
        "base_url": "" 
    }

db = get_database()

# --- 3. 自動化模組 ---
def auto_reset_daily():
    now = datetime.now()
    today_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now > today_3am and db["last_check_date"] < now.date():
        db["inventory"] = [] 
        for s_id in db["shops"]:
            db["shops"][s_id]["queue_status"] = "🟢 免排隊" 
            db["shops"][s_id]["votes"] = {"crowded": set(), "empty": set()}
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

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

TKU_LOCATIONS = {
    "大學城 (Hi-City)": {"lat": 25.1765, "lon": 121.4425},
    "水源街 (圖書館側)": {"lat": 25.1735, "lon": 121.4440},
    "大田寮 (操場側)": {"lat": 25.1710, "lon": 121.4460},
    "捷運站周邊": {"lat": 25.1678, "lon": 121.4456},
    "其他 (自訂座標)": {"lat": 25.1750, "lon": 121.4430}
}

# --- 5. 介面模組 ---

# [A] 軍師後台
def view_admin():
    st.title("🛠️ 餓不死系統 - 總指揮中心")
    st.success("🔓 管理員連線中")
    
    with st.expander("⚙️ 系統設定 (QR Code 修正)", expanded=not bool(db["base_url"])):
        st.info("👇 貼上你的網站網址")
        url_input = st.text_input("系統網址", value=db["base_url"], placeholder="https://...")
        if st.button("儲存網址"):
            if url_input.endswith("/"): url_input = url_input[:-1]
            db["base_url"] = url_input
            st.success("已更新！")
            st.rerun()

    with st.expander("➕ 新增合作店家", expanded=True): 
        with st.form("add_shop"):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("店家名稱")
            location_zone = c2.selectbox("所在區域", list(TKU_LOCATIONS.keys()))
            default_lat = TKU_LOCATIONS[location_zone]["lat"]
            default_lon = TKU_LOCATIONS[location_zone]["lon"]
            c3, c4 = st.columns(2)
            map_url = c3.text_input("Google Maps 連結", placeholder="選填")
            
            if st.form_submit_button("建立"):
                if new_name:
                    new_id = str(uuid.uuid4())[:8]
                    new_key = str(uuid.uuid4())
                    db["shops"][new_id] = {
                        "name": new_name, 
                        "key": new_key,
                        "location": location_zone,
                        "map_url": map_url if map_url else f"https://www.google.com/maps/search/?api=1&query={new_name}+淡江大學",
                        "lat": default_lat,
                        "lon": default_lon,
                        "queue_status": "🟢 免排隊",
                        "votes": {"crowded": set(), "empty": set()}
                    }
                    st.success(f"✅ {new_name} 建立成功！")
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
                
                full_qr_url = f"{db['base_url']}/?shop_key={info['key']}" if db["base_url"] else f"?shop_key={info['key']}"
                
                with col_a:
                    st.image(generate_qr_code(full_qr_url), width=100)
                with col_b:
                    st.subheader(info['name'])
                    st.caption(f"📍 {info['location']}")
                    crowd_votes = len(info.get('votes', {}).get('crowded', set()))
                    empty_votes = len(info.get('votes', {}).get('empty', set()))
                    st.caption(f"📊 投票: 🔴{crowd_votes} | 🟢{empty_votes}")
                    
                with col_c:
                    if st.button("進入店家模式 ➜", key=f"enter_{s_id}"):
                        st.query_params["shop_key"] = info['key']
                        st.rerun()

    st.divider()
    if st.button("進入學生模式 (測試用) ➜", type="primary"):
        st.query_params["test_mode"] = "student" 
        st.rerun()

# [B] 店家端
def view_shop(shop_id):
    if shop_id not in db["shops"]:
        st.error("無效的連結。")
        if st.button("回首頁"): st.query_params.clear(); st.rerun()
        return

    shop_info = db["shops"][shop_id]
    my_items = [x for x in db["inventory"] if x['shop_id'] == shop_id]
    total_qty = sum([x['qty'] for x in my_items])
    is_open = total_qty > 0

    if "queue_status" not in shop_info: shop_info["queue_status"] = "🟢 免排隊"
    if "votes" not in shop_info: shop_info["votes"] = {"crowded": set(), "empty": set()}

    c_title, c_btn = st.columns([3, 1])
    with c_title:
        st.title(f"👨‍🍳 {shop_info['name']}")
        st.info(f"📢 現場路況：**{shop_info['queue_status']}**")

    with c_btn:
        if st.button("登出"):
            st.query_params.clear()
            st.rerun()

    st.divider()
    col_status, col_action = st.columns([2, 1])
    
    with col_status:
        if is_open:
            st.success(f"🟢 **剩食開賣中** (架上 {total_qty} 份)")
        else:
            st.info("⚫ **目前無剩食**")
            
    with col_action:
        if is_open:
            if st.button("🌙 我要打烊 (清空剩食)", type="primary", use_container_width=True):
                db["inventory"] = [x for x in db["inventory"] if x['shop_id'] != shop_id]
                st.toast("已清空架上商品！", icon="🌙")
                time.sleep(1)
                st.rerun()

    st.divider()
    
    st.subheader("🚀 剩食上架")
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

# [C] 學生端 (雙模組設計)
def view_student():
    if st.query_params.get("test_mode") == "student":
        if st.button("⬅️ 結束測試 (回後台)", type="primary"):
            st.query_params.clear()
            st.rerun()
            
    st.title("🍱 餓不死地圖")
    
    # 取得 GPS
    loc = get_geolocation(component_key='user_loc')
    user_lat, user_lon = None, None
    if loc and 'coords' in loc:
        user_lat = loc['coords']['latitude']
        user_lon = loc['coords']['longitude']

    if not db["shops"]:
        st.info("🚧 系統初始化中...")
        st.write("---")
        st.subheader("🔧 創世神入口")
        with st.form("init_admin_login"):
            pwd = st.text_input("請輸入管理密碼", type="password")
            if st.form_submit_button("進入指揮中心"):
                if pwd == "ykk8880820":
                    st.session_state.is_admin_logged_in = True
                    st.rerun()
        return

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
            st.warning("請先輸入 Email 以使用完整功能")

    # --- 核心改動：雙頁籤設計 ---
    tab1, tab2 = st.tabs(["🍽️ 找正餐 (排隊情報)", "🥡 搶剩食 (省錢專區)"])

    # === Tab 1: 正餐排隊模式 ===
    with tab1:
        st.info("📢 這裡顯示店家的「排隊狀況」，讓你知道哪裡人少！")
        
        for s_id, shop in db["shops"].items():
            # 確保資料結構
            if "queue_status" not in shop: shop["queue_status"] = "🟢 免排隊"
            if "votes" not in shop: shop["votes"] = {"crowded": set(), "empty": set()}
            
            # 卡片顯示
            status_color = "red" if "需排隊" in shop["queue_status"] else "green"
            
            with st.container(border=True):
                c1, c2 = st.columns([3, 2])
                with c1:
                    st.subheader(shop['name'])
                    st.caption(f"📍 {shop['location']}")
                    st.markdown(f"狀態：**:{status_color}[{shop['queue_status']}]**")
                    st.link_button("📍 導航去吃", shop['map_url'])
                
                with c2:
                    st.write("🚶 **現場人多嗎？**")
                    # GPS 檢查
                    distance = 9999
                    if user_lat and user_lon:
                        distance = calculate_distance(user_lat, user_lon, shop['lat'], shop['lon'])
                    
                    GEOFENCE_RADIUS = 5000 # 測試用 5000，上線改 50
                    
                    if not email:
                        st.caption("登入後可回報")
                    elif user_lat is None:
                        st.caption("定位中...")
                    elif distance > GEOFENCE_RADIUS:
                        st.caption(f"距離太遠 ({int(distance)}m)")
                    else:
                        b_col1, b_col2 = st.columns(2)
                        if b_col1.button("🔴 人多", key=f"crowd_{s_id}"):
                            shop["votes"]["crowded"].add(email)
                            shop["votes"]["empty"].discard(email)
                            st.toast("已回報：人多")
                            # 檢查票數
                            if len(shop["votes"]["crowded"]) >= 5: shop["queue_status"] = "🔴 需排隊"
                            
                        if b_col2.button("🟢 沒人", key=f"empty_{s_id}"):
                            shop["votes"]["empty"].add(email)
                            shop["votes"]["crowded"].discard(email)
                            st.toast("已回報：沒人")
                            if len(shop["votes"]["empty"]) >= 5: shop["queue_status"] = "🟢 免排隊"
    
    # === Tab 2: 剩食搶購模式 ===
    with tab2:
        st.info("💰 這裡顯示店家釋出的「限量剩食」，手慢無！")
        
        # 篩選有剩食的店家
        active_items = [x for x in db["inventory"] if x['qty'] > 0]
        
        if not active_items:
            st.warning("😴 目前沒有任何店家釋出剩食。")
        else:
            for item in active_items:
                shop = db["shops"].get(item['shop_id'])
                if not shop: continue
                
                user = db["users"].get(email) if email else None
                last_shop_buy = user['last_buy_time'].get(item['shop_id'], 0) if user else 0
                is_cooldown = (time.time() - last_shop_buy) < 600

                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    c1.subheader(f"{shop['name']}")
                    c1.write(f"🍱 **{item['item']}**")
                    c1.markdown(f"💰 **${item['price']}**")
                    c1.caption(f"剩餘: {item['qty']} | 上架: {item['time']}")
                    
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

# --- 6. 路由 (Router) ---
shop_key = st.query_params.get("shop_key", None)
test_mode = st.query_params.get("test_mode", None)

target_shop = None
if shop_key:
    for s_id, info in db["shops"].items():
        if info['key'] == shop_key:
            target_shop = s_id
            break

if target_shop:
    view_shop(target_shop)
elif test_mode == "student":
    view_student()
else:
    if st.session_state.get("is_admin_logged_in"):
        view_admin()
    else:
        if db["shops"]:
            with st.sidebar:
                st.divider()
                with st.expander("🔧 系統管理"):
                    pwd = st.text_input("密碼", type="password")
                    if pwd == "ykk8880820":
                        st.success("驗證成功")
                        if st.button("進入指揮中心", type="primary"):
                            st.session_state.is_admin_logged_in = True
                            st.rerun()
            view_student()
        else:
            view_student()
