import streamlit as st
import pandas as pd
import random
import datetime
import json
import gspread
from google.oauth2.service_account import Credentials

# --- 1. ページ設定 ---
st.set_page_config(page_title="献立自動化アプリ", page_icon="🍳", layout="centered")

# --- 2. ログイン認証 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("ログイン")
        password = st.text_input("パスワードを入力", type="password")
        if st.button("ログイン"):
            # Secretsに設定したパスワードと照合
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

# データを読み込む関数
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

# 初回起動時にデータを読み込む
if "data_loaded" not in st.session_state:
    load_data()
    st.session_state.data_loaded = True
    st.session_state.last_menu = []
    st.session_state.current_menu = []
    st.session_state.menu_gen_id = 0

# 冷蔵庫のデータをスプレッドシートに上書きする関数
def update_inventory_sheet():
    inventory_ws.clear()
    data = [["食材名"]] + [[x] for x in st.session_state.inventory]
    inventory_ws.update(values=data, range_name="A1")

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
    pool_df = available_df[~available_df["料理名"].isin(st.session_state.last_menu)]
    
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

    st.session_state.last_menu = selected.copy()
    st.session_state.current_menu = selected.copy()

def update_menu_selection(index, key):
    st.session_state.current_menu[index] = st.session_state[key]


# --- 5. 画面UI構築 ---
page = st.sidebar.radio("メニュー", ["🏠 ホーム", "🍳 レシピ管理", "❄️ 冷蔵庫管理"])
st.sidebar.write("---")
st.sidebar.write(f"現在の季節判定: **{current_season}**")

# 手動で最新のデータを読み込むボタン（別端末で更新した時用）
if st.sidebar.button("🔁 最新のデータに更新"):
    load_data()
    st.sidebar.success("データを最新にしました！")

# ==========================================
# 🏠 ホーム画面
# ==========================================
if page == "🏠 ホーム":
    st.title("今週の献立＆買い物")
    
    with st.expander("❄️ 冷蔵庫の在庫を追加・確認", expanded=False):
        col_in1, col_in2 = st.columns([3, 1])
        with col_in1:
            home_stock = st.text_input("食材を追加", key="home_stock_input")
        with col_in2:
            st.write("")
            st.write("")
            if st.button("追加", key="home_stock_btn"):
                if home_stock and home_stock not in st.session_state.inventory:
                    st.session_state.inventory.append(home_stock.strip())
                    inventory_ws.append_row([home_stock.strip()]) # シートに書き込み
                    st.rerun()
        
        if st.session_state.inventory:
            st.write("【現在の在庫】※タップで消費（削除）")
            for item in st.session_state.inventory:
                if st.button(f"🗑 {item}", key=f"del_home_{item}"):
                    st.session_state.inventory.remove(item)
                    update_inventory_sheet() # シートから削除
                    st.rerun()
    st.write("")
    
    days_to_plan = st.slider("何日分の献立を作りますか？", 1, 7, 3)
    if st.button(f"{days_to_plan}日分の献立を自動生成", type="primary"):
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
        st.write("右上のマークをタップしてコピーできます。")
        st.code(copy_text, language="text")

# ==========================================
# 🍳 レシピ管理画面
# ==========================================
elif page == "🍳 レシピ管理":
    st.title("レシピの管理")
    st.dataframe(st.session_state.recipes, use_container_width=True)
    
    st.subheader("新しいレシピを追加")
    with st.form("add_recipe_form"):
        new_name = st.text_input("料理名")
        new_diff = st.slider("難易度", 1, 5, 3)
        new_ings = st.text_input("必要な食材（カンマ `,` 区切りで入力）", placeholder="豚肉, キャベツ, 味噌")
        season_options = ["通年", "春", "夏", "秋", "冬"]
        new_seasons = st.multiselect("季節を選択", season_options, default=["通年"])
        
        if st.form_submit_button("追加する"):
            if new_name and new_ings and new_seasons:
                if new_name in st.session_state.recipes["料理名"].values:
                    st.error(f"「{new_name}」はすでに登録されています！")
                else:
                    new_seasons_str = ", ".join(new_seasons)
                    
                    # スプレッドシートに書き込み
                    recipe_ws.append_row([new_name, new_diff, new_ings, new_seasons_str])
                    
                    # 画面（セッション）も更新
                    new_row = pd.DataFrame({
                        "料理名": [new_name], 
                        "難易度": [new_diff], 
                        "食材": [new_ings], 
                        "季節": [new_seasons_str]
                    })
                    st.session_state.recipes = pd.concat([st.session_state.recipes, new_row], ignore_index=True)
                    st.success(f"「{new_name}」を追加しました！")
                    st.rerun()
            else:
                st.error("入力項目に不足があります。")

# ==========================================
# ❄️ 冷蔵庫管理画面
# ==========================================
elif page == "❄️ 冷蔵庫管理":
    st.title("冷蔵庫の在庫")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        new_stock = st.text_input("食材を追加", key="page_stock_input")
    with col2:
        st.write("")
        st.write("")
        if st.button("追加", key="page_stock_btn"):
            if new_stock and new_stock not in st.session_state.inventory:
                st.session_state.inventory.append(new_stock.strip())
                inventory_ws.append_row([new_stock.strip()]) # シートに書き込み
                st.rerun()
                
    st.divider()
    for item in st.session_state.inventory:
        colA, colB = st.columns([3, 1])
        with colA:
            st.write(f"- {item}")
        with colB:
            if st.button("消費", key=f"del_page_{item}"):
                st.session_state.inventory.remove(item)
                update_inventory_sheet() # シートから削除
                st.rerun()
