import streamlit as st
import pandas as pd
import random
import datetime
import json
import gspread
from google.oauth2.service_account import Credentials

# --- 1. ページ設定 ---
st.set_page_config(page_title="献立自動化", page_icon="🍳", layout="centered")

# --- 📱 iPhone標準アプリ風カスタムCSS ---
st.markdown("""
<style>
    .stApp {
        background-color: #f2f2f7;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    div[data-testid="stForm"], div[data-testid="stExpander"] > details, div[data-testid="stDataFrame"] {
        background-color: #ffffff;
        border-radius: 12px;
        border: none;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        padding: 10px;
    }
    div[data-testid="stButton"] > button, div[data-testid="stFormSubmitButton"] > button {
        border-radius: 10px;
        font-weight: 600;
    }
    div[data-testid="stButton"] > button[kind="primary"], div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
        background-color: #007aff;
        color: white;
        border: none;
    }
    div[data-testid="stButton"] > button[kind="secondary"], div[data-testid="stFormSubmitButton"] > button[kind="secondary"] {
        background-color: #ffffff;
        color: #007aff;
        border: 1px solid #007aff;
    }
    button[data-baseweb="tab"] {
        font-weight: bold;
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 5rem;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. ログイン認証 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("ログイン")
        password = st.text_input("パスワードを入力", type="password")
        if st.button("ログイン", type="primary"):
            if password == str(st.secrets.get("password", "1234")):
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        return False
    return True

if not check_password():
    st.stop()

# --- 3. スプレッドシート連携（初期化） ---
@st.cache_resource
def init_connection():
    creds_json = json.loads(st.secrets["google_credentials"])
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    client = gspread.authorize(creds)
    return client

client = init_connection()
sheet = client.open_by_url(st.secrets["sheet_url"])
recipe_ws = sheet.worksheet("レシピ")
inventory_ws = sheet.worksheet("冷蔵庫")
history_ws = sheet.worksheet("履歴") # ← 新しく追加した履歴シート

def load_data():
    recipes_records = recipe_ws.get_all_records()
    if recipes_records:
        st.session_state.recipes = pd.DataFrame(recipes_records)
    else:
        st.session_state.recipes = pd.DataFrame(columns=["料理名", "難易度", "食材", "季節"])
        
    inv_records = inventory_ws.col_values(1)
    if len(inv_records) > 1:
        st.session_state.inventory = inv_records[1:]
    else:
        st.session_state.inventory = []

    # 履歴（前回の献立）を読み込む
    hist_records = history_ws.col_values(1)
    if len(hist_records) > 1:
        st.session_state.last_menu = hist_records[1:]
    else:
        st.session_state.last_menu = []

if "data_loaded" not in st.session_state:
    load_data()
    st.session_state.data_loaded = True
    st.session_state.current_menu = []
    st.session_state.menu_gen_id = 0

def update_inventory_sheet():
    inventory_ws.clear()
    data = [["食材名"]] + [[x] for x in st.session_state.inventory]
    inventory_ws.update(range_name="A1", values=data)

# 前回の献立をスプレッドシートに保存する関数
def update_history_sheet():
    history_ws.clear()
    data = [["前回献立"]] + [[x] for x in st.session_state.last_menu]
    history_ws.update(range_name="A1", values=data)

# --- 4. 季節判定＆献立生成ロジック ---
def get_current_season():
    month = datetime.datetime.now().month
    if 3 <= month <= 5:
        return "春"
    elif 6 <= month <= 8:
        return "夏"
    elif 9 <= month <= 11:
        return "秋"
    else:
        return "冬"

current_season = get_current_season()

def is_in_season(season_str, current):
    seasons = [s.strip() for s in str(season_str).split(",")]
    return "通年" in seasons or current in seasons

def generate_menu(days=3):
    st.session_state.menu_gen_id += 1
    df = st.session_state.recipes
    available_df = df[df["季節"].apply(lambda x: is_in_season(x, current_season))]
    
    # 完全に前回の履歴を除外する
    pool_df = available_df[~available_df["料理名"].isin(st.session_state.last_menu)]
    
    # 万が一、レシピの登録数が少なすぎて（前回分を除くと日数が足りない場合）は、仕方なく前回分も解禁する
    if len(pool_df) < days:
        pool_df = available_df
        st.session_state.last_menu = []

    selected = []
    high_diff_count = 0
    
    while len(selected) < days:
        if len(pool_df) == 0:
            pool_df = available_df
            if len(pool_df) == 0:
                break
                
        shuffled_df = pool_df.sample(frac=1).reset_index(drop=True)
        for _, row in shuffled_df.iterrows():
            if len(selected) == days:
                break
            recipe_name = row["料理名"]
            if recipe_name in selected:
                continue
            if int(row["難易度"]) >= 4:
                if high_diff_count == 0:
                    selected.append(recipe_name)
                    high_diff_count += 1
            else:
                selected.append(recipe_name)
        pool_df = pool_df[~pool_df["料理名"].isin(selected)]

    # 決定した献立を前回の履歴として保存する
    st.session_state.last_menu = selected.copy()
    st.session_state.current_menu = selected.copy()
    update_history_sheet()

def update_menu_selection(index, key):
    # 手動でドロップダウンを変更した場合も履歴に上書きする
    st.session_state.current_menu[index] = st.session_state[key]
    st.session_state.last_menu = st.session_state.current_menu.copy()
    update_history_sheet()


# --- 5. 画面UI構築 ---
st.title("🍳 献立アプリ")

page = st.radio("メニュー", ["🏠 ホーム", "🍳 レシピ", "❄️ 冷蔵庫"], horizontal=True, label_visibility="collapsed")

col_a, col_b = st.columns([3, 1])
with col_a:
    st.caption(f"現在の季節: **{current_season}**")
with col_b:
    if st.button("🔄 更新", help="別端末などで編集した最新データを読み込みます"):
        load_data()
        st.rerun()

st.write("")

# ==========================================
# 🏠 ホーム画面
# ==========================================
if page == "🏠 ホーム":
    with st.expander("❄️ 冷蔵庫の在庫を追加・確認", expanded=False):
        col_in1, col_in2 = st.columns([3, 1])
        with col_in1:
            home_stock = st.text_input("食材を追加", key="home_stock_input")
        with col_in2:
            st.write("")
            st.write("")
            if st.button("追加", key="home_stock_btn", type="primary"):
                if home_stock and home_stock not in st.session_state.inventory:
                    st.session_state.inventory.append(home_stock.strip())
                    inventory_ws.append_row([home_stock.strip()])
                    st.rerun()
        
        if st.session_state.inventory:
            st.write("【タップで消費（削除）】")
            for item in st.session_state.inventory:
                if st.button(f"🗑 {item}", key=f"del_home_{item}"):
                    st.session_state.inventory.remove(item)
                    update_inventory_sheet()
                    st.rerun()
    st.write("")
    
    days_to_plan = st.slider("何日分の献立を作りますか？", 1, 7, 3)
    if st.button(f"{days_to_plan}日分の献立を自動生成", type="primary", use_container_width=True):
        generate_menu(days_to_plan)

    if st.session_state.current_menu:
        st.subheader("🍽️ 決定した献立")
        df_recipes = st.session_state.recipes
        available_recipes = df_recipes["料理名"].tolist()
        copy_text = "🍳 今週の献立\n\n"
        
        for i, menu_item in enumerate(st.session_state.current_menu):
            if menu_item not in available_recipes:
                available_recipes.append(menu_item)
                
            select_key = f"select_{st.session_state.menu_gen_id}_{i}"
            st.selectbox(
                f"Day {i+1} の献立", 
                options=available_recipes, 
                index=available_recipes.index(menu_item),
                key=select_key,
                on_change=update_menu_selection,
                args=(i, select_key)
            )
            
            current_item = st.session_state.current_menu[i]

            if current_item in df_recipes["料理名"].values:
                row = df_recipes[df_recipes["料理名"] == current_item].iloc[0]
                diff = row["難易度"]
                ings_raw = [item.strip() for item in str(row["食材"]).split(",")]
            else:
                diff = "?"
                ings_raw = ["不明"]

            display_ings = []
            buy_ings_for_copy = []
            for ing in ings_raw:
                if ing in st.session_state.inventory:
                    display_ings.append(f"~{ing}~")
                else:
                    display_ings.append(ing)
                    buy_ings_for_copy.append(ing)
            
            ings_str = ", ".join(display_ings)
            st.caption(f"難易度: {diff}")
            st.markdown(f"🥕 材料: {ings_str}")
            st.divider()

            copy_text += f"【Day {i+1}】{current_item}\n"
            if buy_ings_for_copy:
                copy_text += f"🛒 買うもの: {', '.join(buy_ings_for_copy)}\n\n"
            else:
                copy_text += f"🛒 買うもの: なし\n\n"

        st.subheader("📱 LINE等に共有")
        st.code(copy_text, language="text")

# ==========================================
# 🍳 レシピ管理画面
# ==========================================
elif page == "🍳 レシピ":
    tab_add, tab_edit = st.tabs(["📝 新規追加", "⚙️ 編集・削除"])
    
    with tab_add:
        st.dataframe(st.session_state.recipes, use_container_width=True)
        st.write("---")
        with st.form("add_recipe_form"):
            st.subheader("新しいレシピを登録")
            new_name = st.text_input("料理名")
            new_diff = st.slider("難易度", 1, 5, 3)
            new_ings = st.text_input("必要な食材（カンマ `,` 区切りで入力）", placeholder="豚肉, キャベツ, 味噌")
            season_options = ["通年", "春", "夏", "秋", "冬"]
            new_seasons = st.multiselect("季節を選択", season_options, default=["通年"])
            
            if st.form_submit_button("追加する", type="primary"):
                if new_name and new_ings and new_seasons:
                    if new_name in st.session_state.recipes["料理名"].values:
                        st.error(f"「{new_name}」はすでに登録されています！")
                    else:
                        new_seasons_str = ", ".join(new_seasons)
                        recipe_ws.append_row([new_name, new_diff, new_ings, new_seasons_str])
                        load_data()
                        st.success(f"「{new_name}」を追加しました！")
                        st.rerun()
                else:
                    st.error("入力項目に不足があります。")

    with tab_edit:
        if not st.session_state.recipes.empty:
            target_name = st.selectbox("編集するレシピを選んでください", st.session_state.recipes["料理名"].tolist())
            current_data = st.session_state.recipes[st.session_state.recipes["料理名"] == target_name].iloc[0]
            
            with st.form("edit_recipe_form"):
                edit_name = st.text_input("料理名", value=current_data["料理名"])
                edit_diff = st.slider("難易度を調整", 1, 5, int(current_data["難易度"]))
                edit_ings = st.text_input("必要な食材", value=str(current_data["食材"]))
                
                current_seasons = [s.strip() for s in str(current_data["季節"]).split(",")]
                season_options = ["通年", "春", "夏", "秋", "冬"]
                valid_seasons = [s for s in current_seasons if s in season_options]
                edit_seasons = st.multiselect("季節を選択", season_options, default=valid_seasons)
                
                st.write("")
                col_update, col_del = st.columns(2)
                with col_update:
                    update_btn = st.form_submit_button("🔄 更新する", type="primary")
                with col_del:
                    delete_btn = st.form_submit_button("🗑 削除する")
                    
            if update_btn:
                if edit_name and edit_ings and edit_seasons:
                    if edit_name != target_name and edit_name in st.session_state.recipes["料理名"].values:
                        st.error(f"「{edit_name}」はすでに別のレシピとして登録されています。")
                    else:
                        names_in_sheet = recipe_ws.col_values(1)
                        if target_name in names_in_sheet:
                            row_idx = names_in_sheet.index(target_name) + 1
                            edit_seasons_str = ", ".join(edit_seasons)
                            recipe_ws.update(range_name=f"A{row_idx}:D{row_idx}", values=[[edit_name, edit_diff, edit_ings, edit_seasons_str]])
                            load_data()
                            st.success("レシピを更新しました！")
                            st.rerun()
                else:
                    st.error("入力項目に不足があります。")
                    
            if delete_btn:
                names_in_sheet = recipe_ws.col_values(1)
                if target_name in names_in_sheet:
                    row_idx = names_in_sheet.index(target_name) + 1
                    recipe_ws.delete_rows(row_idx)
                    load_data()
                    st.success(f"「{target_name}」を削除しました。")
                    st.rerun()
        else:
            st.info("登録されているレシピがありません。")

# ==========================================
# ❄️ 冷蔵庫管理画面
# ==========================================
elif page == "❄️ 冷蔵庫":
    st.write("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        new_stock = st.text_input("食材を追加", key="page_stock_input")
    with col2:
        st.write("")
        st.write("")
        if st.button("追加", key="page_stock_btn", type="primary"):
            if new_stock and new_stock not in st.session_state.inventory:
                st.session_state.inventory.append(new_stock.strip())
                inventory_ws.append_row([new_stock.strip()])
                st.rerun()
                
    st.divider()
    for item in st.session_state.inventory:
        colA, colB = st.columns([3, 1])
        with colA:
            st.write(f"- {item}")
        with colB:
            if st.button("消費", key=f"del_page_{item}"):
                st.session_state.inventory.remove(item)
                update_inventory_sheet()
                st.rerun()
