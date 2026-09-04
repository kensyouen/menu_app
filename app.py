import streamlit as st
import pandas as pd
import random, datetime, json, gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image

# --- 1. ページ設定 ---
st.set_page_config(page_title="献立自動化", page_icon="🍳", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #f2f2f7; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    div[data-testid="stForm"], details, div[data-testid="stDataFrame"] {
        background-color: #ffffff; border-radius: 12px; border: none; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 10px;
    }
    div[data-testid="stButton"]>button, div[data-testid="stFormSubmitButton"]>button { border-radius: 10px; font-weight: 600; }
    div[data-testid="stButton"]>button[kind="primary"], div[data-testid="stFormSubmitButton"]>button[kind="primary"] {
        background-color: #007aff; color: white; border: none;
    }
    div[data-testid="stButton"]>button[kind="secondary"], div[data-testid="stFormSubmitButton"]>button[kind="secondary"] {
        background-color: #ffffff; color: #007aff; border: 1px solid #007aff;
    }
    .block-container { padding-top: 2rem; padding-bottom: 5rem; }
</style>
""", unsafe_allow_html=True)

# --- 2. ログイン認証 ---
def check_password():
    if not st.session_state.get("password_correct", False):
        st.title("ログイン")
        if st.button("ログイン", type="primary") if (pwd := st.text_input("パスワード", type="password")) else False:
            if pwd == str(st.secrets.get("password", "1234")):
                st.session_state["password_correct"] = True
                st.rerun()
            else: st.error("パスワードが違います")
        return False
    return True

if not check_password(): st.stop()

# --- 3. スプレッドシート連携 ---
@st.cache_resource(ttl=600)
def get_worksheets():
    creds = Credentials.from_service_account_info(
        json.loads(st.secrets["google_credentials"]), 
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["sheet_url"])
    return sheet.worksheet("レシピ"), sheet.worksheet("冷蔵庫"), sheet.worksheet("履歴")

recipe_ws, inventory_ws, history_ws = get_worksheets()

def load_data():
    req = recipe_ws.get_all_records()
    st.session_state.recipes = pd.DataFrame(req) if req else pd.DataFrame(columns=["料理名", "難易度", "食材", "季節"])
    inv = inventory_ws.col_values(1)
    st.session_state.inventory = inv[1:] if len(inv) > 1 else []
    hist = history_ws.col_values(1)
    st.session_state.last_menu = hist[1:] if len(hist) > 1 else []

if "data_loaded" not in st.session_state:
    load_data()
    st.session_state.update({"data_loaded": True, "current_menu": [], "menu_gen_id": 0})

def update_inventory_sheet():
    inventory_ws.clear()
    inventory_ws.update(range_name="A1", values=[["食材名"]] + [[x] for x in st.session_state.inventory])

def update_history_sheet():
    history_ws.clear()
    history_ws.update(range_name="A1", values=[["前回献立"]] + [[x] for x in st.session_state.last_menu])

# --- AI画像認識（調味料・飲み物除外＆表記ゆれ防止） ---
def analyze_image_with_ai(image_file):
    all_ings = [item.strip() for ings_str in st.session_state.recipes["食材"] for item in str(ings_str).split(",") if item.strip()]
    unique_ings = list(set(all_ings))
    
    prompt = f"""
    画像に写っている食材をすべて抽出し、カンマ区切り（例: 豚肉, にんじん, キャベツ）で出力してください。
    【重要】飲み物（水、お茶、ジュース、お酒など）や、調味料（塩、醤油、砂糖、マヨネーズ、ソースなど）は絶対に抽出対象に含めないでください。
    以下の【登録済み食材リスト】の中に同じものや似ているものがある場合は、必ずリスト内の表記に合わせて出力してください。リストにない場合は一般的な名称で出力してください。
    出力は食材名のカンマ区切りのみとし、それ以外の文章や記号は絶対に含めないでください。
    【登録済み食材リスト】 {', '.join(unique_ings)}
    """
    try:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        # 🔥 古い "gemini-1.5-flash" から 最新の "gemini-3.6-flash" に変更しました！
        response = genai.GenerativeModel('gemini-3.6-flash').generate_content([prompt, Image.open(image_file)])
        return [item.strip() for item in response.text.split(",") if item.strip()]
    except Exception as e:
        st.error(f"AIの解析に失敗しました。詳細: {e}")
        return []

# --- 在庫管理の共通UI ---
def render_inventory_ui(key_prefix):
    t1, t2 = st.tabs(["✍️ 手動", "📷 写真(AI)"])
    with t1:
        c1, c2 = st.columns([3, 1])
        with c1: home_stock = st.text_input("食材名を入力", key=f"{key_prefix}_input")
        with c2:
            st.write(""); st.write("")
            if st.button("追加", key=f"{key_prefix}_btn", type="primary") and home_stock and home_stock not in st.session_state.inventory:
                st.session_state.inventory.append(home_stock.strip())
                inventory_ws.append_row([home_stock.strip()])
                st.rerun()
    with t2:
        if uploaded_file := st.file_uploader("写真をアップロード", type=["jpg", "jpeg", "png"], key=f"{key_prefix}_img"):
            st.image(uploaded_file, caption="アップロード画像", use_container_width=True)
            if st.button("✨ AIで読み取る", key=f"{key_prefix}_ai_btn", type="primary", use_container_width=True):
                with st.spinner("AI解析中..."):
                    if detected := analyze_image_with_ai(uploaded_file):
                        added = [item for item in detected if item not in st.session_state.inventory]
                        for item in added:
                            st.session_state.inventory.append(item)
                            inventory_ws.append_row([item])
                        st.success(f"AIが認識: {', '.join(detected)}\n（{len(added)} 個追加）")
                    else: st.warning("食材を認識できませんでした。")

    if st.session_state.inventory:
        st.write("---")
        for item in st.session_state.inventory:
            c_a, c_b = st.columns([3, 1])
            with c_a: st.write(f"- {item}")
            with c_b:
                if st.button("消費", key=f"del_{key_prefix}_{item}"):
                    st.session_state.inventory.remove(item)
                    update_inventory_sheet()
                    st.rerun()

# --- 4. 季節＆献立生成ロジック ---
def get_current_season():
    m = datetime.datetime.now().month
    return "春" if 3<=m<=5 else "夏" if 6<=m<=8 else "秋" if 9<=m<=11 else "冬"

def is_in_season(season_str, current):
    s = [x.strip() for x in str(season_str).split(",")]
    return "通年" in s or current in s

def generate_menu(days=3):
    st.session_state.menu_gen_id += 1
    avail = st.session_state.recipes[st.session_state.recipes["季節"].apply(lambda x: is_in_season(x, get_current_season()))]
    pool = avail[~avail["料理名"].isin(st.session_state.last_menu)]
    if len(pool) < days:
        pool = avail
        st.session_state.last_menu = []
    sel, high = [], 0
    while len(sel) < days and not pool.empty:
        for _, row in pool.sample(frac=1).iterrows():
            if len(sel) == days: break
            if row["料理名"] in sel: continue
            if int(row["難易度"]) >= 4:
                if high == 0:
                    sel.append(row["料理名"]); high += 1
            else: sel.append(row["料理名"])
        pool = pool[~pool["料理名"].isin(sel)]
    st.session_state.last_menu = sel.copy()
    st.session_state.current_menu = sel.copy()
    update_history_sheet()

def update_menu_selection(index, key):
    st.session_state.current_menu[index] = st.session_state[key]
    st.session_state.last_menu = st.session_state.current_menu.copy()
    update_history_sheet()

# --- 5. 画面UI構築 ---
st.title("🍳 献立アプリ")
page = st.radio("メニュー", ["🏠 ホーム", "🍳 レシピ", "❄️ 冷蔵庫"], horizontal=True, label_visibility="collapsed")
c_a, c_b = st.columns([3, 1])
with c_a: st.caption(f"現在の季節: **{get_current_season()}**")
with c_b:
    if st.button("🔄 更新"): 
        get_worksheets.clear()
        load_data()
        st.rerun()
st.write("")

if page == "🏠 ホーム":
    with st.expander("❄️ 冷蔵庫の在庫を追加・確認", expanded=False): render_inventory_ui("home")
    st.write("")
    days_to_plan = st.slider("何日分の献立を作る？", 1, 7, 3)
    if st.button(f"{days_to_plan}日分の献立を自動生成", type="primary", use_container_width=True): generate_menu(days_to_plan)

    if st.session_state.current_menu:
        st.subheader("🍽️ 決定した献立")
        df_r = st.session_state.recipes
        avail_r = df_r["料理名"].tolist()
        copy_text = "🍳 今週の献立\n\n"
        for i, m_item in enumerate(st.session_state.current_menu):
            if m_item not in avail_r: avail_r.append(m_item)
            sk = f"select_{st.session_state.menu_gen_id}_{i}"
            st.selectbox(f"Day {i+1}", options=avail_r, index=avail_r.index(m_item), key=sk, on_change=update_menu_selection, args=(i, sk))
            c_item = st.session_state.current_menu[i]
            if c_item in df_r["料理名"].values:
                r = df_r[df_r["料理名"] == c_item].iloc[0]
                diff = r["難易度"]
                ings = [x.strip() for x in str(r["食材"]).split(",")]
            else: diff, ings = "?", ["不明"]
            d_ings, b_ings = [], []
            for ing in ings:
                if ing in st.session_state.inventory: d_ings.append(f"~{ing}~")
                else: d_ings.append(ing); b_ings.append(ing)
            st.caption(f"難易度: {diff}")
            st.markdown(f"🥕 材料: {', '.join(d_ings)}")
            st.divider()
            copy_text += f"【Day {i+1}】{c_item}\n🛒 買うもの: {', '.join(b_ings) if b_ings else 'なし'}\n\n"
        st.subheader("📱 LINE等に共有")
        st.code(copy_text, language="text")

elif page == "🍳 レシピ":
    t_add, t_edit = st.tabs(["📝 新規追加", "⚙️ 編集・削除"])
    with t_add:
        st.dataframe(st.session_state.recipes, use_container_width=True)
        with st.form("add_recipe_form"):
            st.subheader("新しいレシピを登録")
            n_name = st.text_input("料理名")
            n_diff = st.slider("難易度", 1, 5, 3)
            n_ings = st.text_input("必要な食材（カンマ `,` 区切りで入力）", placeholder="豚肉, キャベツ, 味噌")
            n_seasons = st.multiselect("季節を選択", ["通年", "春", "夏", "秋", "冬"], default=["通年"])
            if st.form_submit_button("追加する", type="primary"):
                if n_name and n_ings and n_seasons:
                    if n_name in st.session_state.recipes["料理名"].values: st.error("すでに登録されています！")
                    else:
                        s_str = ", ".join(n_seasons)
                        recipe_ws.append_row([n_name, n_diff, n_ings, s_str])
                        get_worksheets.clear()
                        load_data(); st.success(f"「{n_name}」を追加しました！"); st.rerun()
                else: st.error("入力項目に不足があります。")
    with t_edit:
        if not st.session_state.recipes.empty:
            t_name = st.selectbox("編集するレシピを選択", st.session_state.recipes["料理名"].tolist())
            c_data = st.session_state.recipes[st.session_state.recipes["料理名"] == t_name].iloc[0]
            with st.form("edit_recipe_form"):
                e_name = st.text_input("料理名", value=c_data["料理名"])
                e_diff = st.slider("難易度", 1, 5, int(c_data["難易度"]))
                e_ings = st.text_input("必要な食材", value=str(c_data["食材"]))
                c_seasons = [s.strip() for s in str(c_data["季節"]).split(",")]
                e_seasons = st.multiselect("季節を選択", ["通年", "春", "夏", "秋", "冬"], default=[s for s in c_seasons if s in ["通年", "春", "夏", "秋", "冬"]])
                c_upd, c_del = st.columns(2)
                with c_upd: u_btn = st.form_submit_button("🔄 更新", type="primary")
                with c_del: d_btn = st.form_submit_button("🗑 削除")
            if u_btn:
                if e_name and e_ings and e_seasons:
                    if e_name != t_name and e_name in st.session_state.recipes["料理名"].values: st.error("すでに別のレシピとして登録されています。")
                    else:
                        names = recipe_ws.col_values(1)
                        if t_name in names:
                            idx = names.index(t_name) + 1
                            recipe_ws.update(range_name=f"A{idx}:D{idx}", values=[[e_name, e_diff, e_ings, ", ".join(e_seasons)]])
                            get_worksheets.clear()
                            load_data(); st.success("更新しました！"); st.rerun()
                else: st.error("入力項目に不足があります。")
            if d_btn:
                names = recipe_ws.col_values(1)
                if t_name in names:
                    recipe_ws.delete_rows(names.index(t_name) + 1)
                    get_worksheets.clear()
                    load_data(); st.success("削除しました。"); st.rerun()
        else: st.info("登録レシピがありません。")

elif page == "❄️ 冷蔵庫":
    render_inventory_ui("page")
