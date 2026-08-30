import streamlit as st
import pandas as pd
import random
import datetime

# --- 1. ページ設定 ---
st.set_page_config(page_title="献立自動化アプリ", page_icon="🍳", layout="centered")

# --- 2. 簡易ログイン認証 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("ログイン")
        password = st.text_input("パスワードを入力", type="password")
        if st.button("ログイン"):
            if password == "1234":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        return False
    return True

if not check_password():
    st.stop()

# --- 3. 季節を自動判定する関数 ---
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

# --- 4. 初期データ（プレビュー用） ---
if "recipes" not in st.session_state:
    st.session_state.recipes = pd.DataFrame({
        "料理名": ["カレーライス", "肉じゃが", "生姜焼き", "冷やし中華", "ハンバーグ", "鍋料理", "そうめん"],
        "難易度": [2, 3, 2, 2, 4, 2, 1],
        "食材": ["豚肉, 玉ねぎ, にんじん, じゃがいも, カレールー", 
               "豚肉, じゃがいも, にんじん, 玉ねぎ, しらたき", 
               "豚肉, 玉ねぎ, キャベツ, しょうが", 
               "中華麺, きゅうり, ハム, 卵, トマト", 
               "ひき肉, 玉ねぎ, 卵, 牛乳, パン粉", 
               "白菜, 豚バラ, 長ねぎ, 豆腐, きのこ",
               "そうめん, めんつゆ, ねぎ"],
        "季節": ["通年", "通年, 秋, 冬", "通年", "夏", "通年", "冬", "夏"]
    })

if "inventory" not in st.session_state:
    st.session_state.inventory = ["玉ねぎ", "じゃがいも", "卵"]
if "last_menu" not in st.session_state:
    st.session_state.last_menu = []
if "current_menu" not in st.session_state:
    st.session_state.current_menu = []

# --- 5. 献立生成・更新ロジック ---
def is_in_season(season_str, current):
    seasons = [s.strip() for s in season_str.split(",")]
    return "通年" in seasons or current in seasons

def generate_menu(days=3):
    df = st.session_state.recipes
    available_df = df[df["季節"].apply(lambda x: is_in_season(x, current_season))]
    available_df = available_df[~available_df["料理名"].isin(st.session_state.last_menu)]
    
    if len(available_df) < days:
        st.warning("条件に合うレシピが足りないため、履歴をリセットして生成します。")
        available_df = df[df["季節"].apply(lambda x: is_in_season(x, current_season))]
        st.session_state.last_menu = []

    selected = []
    high_diff_count = 0
    shuffled_df = available_df.sample(frac=1).reset_index(drop=True)
    
    for _, row in shuffled_df.iterrows():
        if len(selected) == days:
            break
        if row["難易度"] >= 4:
            if high_diff_count == 0:
                selected.append(row["料理名"])
                high_diff_count += 1
        else:
            selected.append(row["料理名"])

    st.session_state.last_menu = selected
    st.session_state.current_menu = selected

# 手動でドロップダウンを変更した際に確実にデータを更新するための関数
def update_menu_selection(index):
    st.session_state.current_menu[index] = st.session_state[f"select_{index}"]


# --- 6. 画面UI構築 ---
page = st.sidebar.radio("メニュー", ["🏠 ホーム", "🍳 レシピ管理", "❄️ 冷蔵庫管理"])
st.sidebar.write("---")
st.sidebar.write(f"現在の季節判定: **{current_season}**")

# ==========================================
# 🏠 ホーム画面
# ==========================================
if page == "🏠 ホーム":
    st.title("今週の献立＆買い物")
    
    # --- 冷蔵庫の在庫を追加・確認 ---
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
                    st.rerun()
        
        if st.session_state.inventory:
            st.write("【現在の在庫】※タップで消費（削除）")
            for item in st.session_state.inventory:
                if st.button(f"🗑 {item}", key=f"del_home_{item}"):
                    st.session_state.inventory.remove(item)
                    st.rerun()
    st.write("")
    
    # --- 献立生成 ---
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
                
            # ドロップダウン（変更時に確実に update_menu_selection を呼び出す）
            st.selectbox(
                f"Day {i+1} の献立", 
                options=available_recipes, 
                index=available_recipes.index(menu_item),
                key=f"select_{i}",
                on_change=update_menu_selection,
                args=(i,)
            )
            
            # ドロップダウンの変更が反映された最新のメニューを取得
            current_item = st.session_state.current_menu[i]

            if current_item in df_recipes["料理名"].values:
                row = df_recipes[df_recipes["料理名"] == current_item].iloc[0]
                diff = row["難易度"]
                ings_raw = [item.strip() for item in row["食材"].split(",")]
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
                new_seasons_str = ", ".join(new_seasons)
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
                st.rerun()
                
    st.divider()
    for item in st.session_state.inventory:
        colA, colB = st.columns([3, 1])
        with colA:
            st.write(f"- {item}")
        with colB:
            if st.button("消費", key=f"del_page_{item}"):
                st.session_state.inventory.remove(item)
                st.rerun()
