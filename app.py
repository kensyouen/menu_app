import streamlit as st
import pandas as pd
import random

# --- 1. ページ設定 ---
st.set_page_config(page_title="献立自動化アプリ", page_icon="🍳", layout="centered")

# --- 2. 簡易ログイン認証（st.secrets想定） ---
# ※ローカルで試す場合は、.streamlit/secrets.tomlを作成するか、
# 一時的にパスワードをベタ書きしてテストします。
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("ログイン")
        password = st.text_input("パスワードを入力してください", type="password")
        # プレビュー用のダミーパスワード（本番では st.secrets["password"] に変更）
        if st.button("ログイン"):
            if password == "1234": # 仮のパスワード
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        return False
    return True

if not check_password():
    st.stop()

# --- 3. セッションステート（初期データ）の準備 ---
if "recipes" not in st.session_state:
    # ダミーのレシピデータ
    st.session_state.recipes = pd.DataFrame({
        "料理名": ["カレーライス", "肉じゃが", "生姜焼き", "冷やし中華", "ハンバーグ", "麻婆豆腐"],
        "難易度": [2, 3, 2, 2, 4, 3],
        "食材": ["豚肉, 玉ねぎ, にんじん, じゃがいも, カレールー", 
               "豚肉, じゃがいも, にんじん, 玉ねぎ, しらたき", 
               "豚肉, 玉ねぎ, キャベツ, しょうが", 
               "中華麺, きゅうり, ハム, 卵, トマト", 
               "ひき肉, 玉ねぎ, 卵, 牛乳, パン粉", 
               "ひき肉, 豆腐, ねぎ, にんにく, 豆板醤"]
    })

if "inventory" not in st.session_state:
    # 冷蔵庫の在庫データ
    st.session_state.inventory = ["玉ねぎ", "じゃがいも", "卵"]

if "last_menu" not in st.session_state:
    st.session_state.last_menu = [] # 前回の献立

if "current_menu" not in st.session_state:
    st.session_state.current_menu = [] # 今回の献立

# --- 4. 献立自動生成ロジック ---
def generate_menu(days=3):
    df = st.session_state.recipes
    # 前回の献立を除外
    available_df = df[~df["料理名"].isin(st.session_state.last_menu)]
    
    if len(available_df) < days:
        st.warning("候補となるレシピが不足しています。履歴をリセットします。")
        available_df = df
        st.session_state.last_menu = []

    selected = []
    high_difficulty_count = 0

    # シャッフルして上から選んでいく
    shuffled_df = available_df.sample(frac=1).reset_index(drop=True)
    
    for _, row in shuffled_df.iterrows():
        if len(selected) == days:
            break
        # 難易度4以上の料理は最大1つまでとするルール
        if row["難易度"] >= 4:
            if high_difficulty_count == 0:
                selected.append(row["料理名"])
                high_difficulty_count += 1
        else:
            selected.append(row["料理名"])

    st.session_state.last_menu = selected # 次回のために履歴を保存
    st.session_state.current_menu = selected

# --- 5. 画面切り替え（サイドバー） ---
page = st.sidebar.radio("メニュー", ["🏠 ホーム", "🍳 レシピ管理", "❄️ 冷蔵庫管理"])

# ==========================================
# 🏠 ホーム画面
# ==========================================
if page == "🏠 ホーム":
    st.title("今週の献立＆買い物リスト")
    
    days_to_plan = st.slider("何日分の献立を作りますか？", 1, 7, 3)
    if st.button(f"{days_to_plan}日分の献立を自動生成", type="primary"):
        generate_menu(days_to_plan)

    if st.session_state.current_menu:
        st.subheader("🍽️ 決定した献立")
        df_recipes = st.session_state.recipes
        
        # 献立リストと個別の変更（再生成）処理
        new_menu = []
        for i, menu_item in enumerate(st.session_state.current_menu):
            col1, col2 = st.columns([3, 1])
            with col1:
                # 難易度を表示
                diff = df_recipes[df_recipes["料理名"] == menu_item]["難易度"].values[0]
                st.write(f"Day {i+1}: **{menu_item}** (難易度: {diff})")
            new_menu.append(menu_item)
            # ※個別変更機能はUIが複雑になるためプレビュー段階では割愛。必要であれば実装します。

        st.divider()
        
        # 買い物リストの生成
        st.subheader("🛒 必要な食材リスト")
        all_ingredients = []
        for menu_item in st.session_state.current_menu:
            ing_str = df_recipes[df_recipes["料理名"] == menu_item]["食材"].values[0]
            # カンマ区切りの文字列をリスト化し、空白を削除
            ings = [item.strip() for item in ing_str.split(",")]
            all_ingredients.extend(ings)
        
        # 重複を削除
        unique_ingredients = sorted(list(set(all_ingredients)))
        
        # 冷蔵庫の在庫と照合して表示
        buy_list = []
        stock_list = []
        for item in unique_ingredients:
            if item in st.session_state.inventory:
                stock_list.append(item)
            else:
                buy_list.append(item)
                
        if buy_list:
            st.write("🔴 **買うもの**")
            for item in buy_list:
                st.write(f"- [ ] {item}")
        else:
            st.success("買うものはありません！")
            
        if stock_list:
            st.write("🟢 **家にあるもの（不要）**")
            for item in stock_list:
                st.markdown(f"- ~{item}~ (在庫あり)")

# ==========================================
# 🍳 レシピ管理画面
# ==========================================
elif page == "🍳 レシピ管理":
    st.title("レシピの管理")
    st.write("現在登録されているレシピ一覧です。")
    
    st.dataframe(st.session_state.recipes, use_container_width=True)
    
    st.subheader("新しいレシピを追加")
    with st.form("add_recipe_form"):
        new_name = st.text_input("料理名")
        new_diff = st.slider("難易度", 1, 5, 3)
        new_ings = st.text_input("必要な食材（カンマ `,` 区切りで入力）", placeholder="豚肉, キャベツ, 味噌")
        
        submitted = st.form_submit_button("追加する")
        if submitted:
            if new_name != "" and new_ings != "":
                new_row = pd.DataFrame({"料理名": [new_name], "難易度": [new_diff], "食材": [new_ings]})
                st.session_state.recipes = pd.concat([st.session_state.recipes, new_row], ignore_index=True)
                st.success(f"「{new_name}」を追加しました！")
                st.rerun()
            else:
                st.error("料理名と食材は必須です。")

# ==========================================
# ❄️ 冷蔵庫管理画面
# ==========================================
elif page == "❄️ 冷蔵庫管理":
    st.title("冷蔵庫の在庫")
    st.write("家にある食材を登録しておくと、買い物リストで不要として表示されます。")
    
    # 在庫の追加
    col1, col2 = st.columns([3, 1])
    with col1:
        new_stock = st.text_input("食材を追加")
    with col2:
        st.write("")
        st.write("")
        if st.button("追加"):
            if new_stock and new_stock not in st.session_state.inventory:
                st.session_state.inventory.append(new_stock.strip())
                st.rerun()
                
    st.divider()
    st.write("**現在の在庫:**")
    
    # 削除機能付きのリスト表示
    for item in st.session_state.inventory:
        colA, colB = st.columns([3, 1])
        with colA:
            st.write(f"- {item}")
        with colB:
            if st.button("消費した", key=f"del_{item}"):
                st.session_state.inventory.remove(item)
                st.rerun()
