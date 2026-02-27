import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ページのタイトルとアイコンを設定
st.set_page_config(page_title="Ryuon_Apricot_Equipmentdata")

DB_FILE = "equipment.db"

@st.cache_resource
def load_data():
    """SQLite DB からデータを読み込む"""
    conn = sqlite3.connect(DB_FILE)

    equipments_list = ["武器", "防具", "装飾"]
    rarelity_order = ['ur', 'ksr', 'ssr']
    df_list = []

    for equipments in equipments_list:
        equipment_df_concat_list = []
        for  rarelity in rarelity_order:
            sheet_name = f"{rarelity}{equipments}"
            df = pd.read_sql(f"""
WITH new_equipment_img_scraping AS (
    SELECT DISTINCT
        装備名
        , BASE64
        , レアリティ
    FROM equipment_img_scraping
    )
SELECT 
    s.装備名
    , e.BASE64 AS 画像
    , 装備番号
    , s.レアリティ
    , s.体力
    , s.攻撃力
    , s.防御力
    , s.会心率
    , s.命中率
    , s.回避率
    , s.アビリティ
    , s.アビリティカテゴリ
FROM '{sheet_name}' AS s
LEFT JOIN new_equipment_img_scraping AS e
ON s.装備名 = e.装備名 AND s.レアリティ = e.レアリティ
                              """
                              , conn)
            equipment_df_concat_list.append(df)
        stay_df = pd.read_sql(f"""WITH new_equipment_img_scraping AS (
    SELECT DISTINCT
        装備名
        , BASE64
        , レアリティ
    FROM equipment_img_scraping
    )
SELECT 
    s.装備名
    , e.BASE64 AS 画像
    , 装備番号
    , s.レアリティ
    , s.体力
    , s.攻撃力
    , s.防御力
    , s.会心率
    , s.命中率
    , s.回避率
    , s.アビリティ
    , s.アビリティカテゴリ
FROM non_check_equipments AS s
LEFT JOIN new_equipment_img_scraping AS e
ON s.装備名 = e.装備名 AND s.レアリティ = e.レアリティ
WHERE s.装備種類 = '{equipments}'""", conn)
        equipment_df_concat_list.append(stay_df)
        df = pd.concat(equipment_df_concat_list)
        df = df.sort_values('装備番号', ignore_index=True)
        df = df.replace('', pd.NA)
        df['check'] = False
        # チェック列を一番左に移動
        columns = ['check'] + [col for col in df.columns if col != 'check']
        df = df[columns]
        df['アビリティカテゴリ'] = df['アビリティカテゴリ'].fillna('アビリティなし')
        df_list.append(df)

    # アビリティカテゴリ
    df_category = pd.read_sql("SELECT * FROM 'ability_category'", conn)
    df_nan = pd.DataFrame({'アビリティカテゴリ分類': ['アビリティなし']})
    df_category = pd.concat([df_category, df_nan])

    conn.close()
    return df_list[0], df_list[1], df_list[2], df_category


def rarity_select_list_ui():
    rarity_list = ['UR', 'KSR', 'SSR']
    # 選択解除ボタン設定中
    # cols = st.columns([1, 1])  # 幅の比率を調整
    # # セッション状態で選択状態を管理（初期状態は全選択）
    # # if "rarity_state" not in st.session_state:
    # st.session_state["rarity_state"] = rarity_list
    # with cols[0]:
    #     st.write("### レアリティ")
    # with cols[1]:
    #     if st.button('選択解除',key= 'rarity_button'):
    #         st.session_state["rarity_state"] = rarity_list

    st.write("### レアリティ")
    # レアリティ選択ピル
    rarity_select_list = st.pills(
        label= 'レアリティ',
        options=rarity_list,
        selection_mode="multi",
        # default=st.session_state["rarity_state"],
        default= rarity_list,
    )
    # セッション状態を更新（選択解除ボタン設定中）
    # st.session_state["rarity_state"] = rarity_select_list
    return rarity_select_list

def status_select_list_ui():
    status_list = ['体力', '攻撃力', '防御力', '会心率', '命中率', '回避率']
    # 選択解除ボタン設定中
    # # セッション状態で選択状態を管理（初期状態は全選択）
    # if "status_state" not in st.session_state:
    #     st.session_state["status_state"] = []
    # # サイドバー内で「ステータス」と「選択解除」を横並びに配置
    # cols = st.columns([1, 1])  # 幅の比率を調整
    # with cols[0]:
    #     st.write("### ステータス")
    # with cols[1]:
    #     if st.button('選択解除',key= 'status_button'):
    #         st.session_state["status_state"] = []
    st.write("### ステータス")
    status_select_list = st.pills(
        label= 'ステータス',
        options=status_list,
        selection_mode="multi",
        # default=st.session_state["status_state"],
        default=[],
    )
    # セッション状態を更新 選択解除ボタン設定中
    # st.session_state["status_state"] = status_select_list
    return status_select_list

def ability_select_list_ui(category_df):
    st.write("### アビリティ")
    # アビリティ名のリストを作成
    ability_name_list = category_df['アビリティカテゴリ分類'].unique()
    # # Nanを削除
    # ability_name_list = ability_name_list[1:]
    #複数選択
    ability_select_list = st.multiselect(label='アビリティを選択してください',options = ability_name_list,label_visibility= 'collapsed')
    
    if len(ability_select_list) == 0:
        ability_select_list = ability_name_list
    return ability_select_list

# resetボタンを押したときに全選択されるようにする案
# def equipment_col_select_ui():
#     equipment_col_list = ['レアリティ', '体力', '攻撃力', '防御力', '会心率', '命中率', '回避率', 'アビリティ']
    
#     # 初期状態のセッション設定
#     if "col_state" not in st.session_state:
#         st.session_state["col_state"] = equipment_col_list

#     # UIのレイアウト
#     cols = st.columns([2, 1, 1])
#     with cols[0]:
#         st.write("### 表示項目")
#     with cols[1]:
#         if st.button('全選択', key='all_select_col_button'):
#             st.session_state["col_state"] = equipment_col_list
#     with cols[2]:
#         if st.button('リセット', key='all_reset_col_button'):
#             st.session_state["col_state"] = []

#     # `st.multiselect` の選択項目をセッション状態で管理
#     equipment_col_select_list = st.multiselect(
#         label='',
#         options=equipment_col_list,
#         default=st.session_state["col_state"],
#         label_visibility='collapsed'
#     )
#     # セッション状態を更新
#     if set(equipment_col_select_list) != set(st.session_state["col_state"]):
#         st.session_state["col_state"] = equipment_col_select_list

#     return st.session_state["col_state"]


def equipment_col_select_ui():
    equipment_col_list = ['画像','レアリティ', '体力', '攻撃力', '防御力', '会心率', '命中率', '回避率', 'アビリティ']
    st.write("### 表示項目")
    # `st.multiselect` の選択項目をセッション状態で管理
    equipment_col_select_list = st.multiselect(
        label='表示項目',
        options=equipment_col_list,
        default=equipment_col_list,
        label_visibility='collapsed'
    )
    return equipment_col_select_list


def index_filtered_df(df,rarity_select_list,status_select_list,ability_select_list):
    df_col = df.copy()
    df = df[df['レアリティ'].isin(rarity_select_list)]
    for status in status_select_list:
        df = df[df[status].notnull() == True]
    df = df[df['アビリティカテゴリ'].apply(lambda x: any(ab in x for ab in ability_select_list) if pd.notnull(x) else False)]
    if df.shape[1]==0:
        df = pd.DataFrame(columns=df_col.columns)
    return df

def equipment_checked_df_list(equipment, filtered_equipment_df, equipment_col_select_list):
    session_key = f"{equipment}_checked_rows"
    if session_key not in st.session_state:
        st.session_state[session_key] = []
    # 画像の読み込み
    col_cfg = {"画像": st.column_config.ImageColumn("画像")}
    
    equipment_df = pd.concat([filtered_equipment_df[['check', '装備名']], filtered_equipment_df[equipment_col_select_list]],axis=1)
    equipment_df["check"] = equipment_df.index.isin(st.session_state[session_key])
    equipment_df = st.data_editor(equipment_df,disabled=(col for col in equipment_col_select_list + ["装備名"]),key=f"{equipment}_df", column_config=col_cfg)
    st.session_state[session_key] = filtered_equipment_df[equipment_df["check"]]['装備番号'].tolist()
    select_index_num_list = filtered_equipment_df[equipment_df["check"]]['装備番号'].tolist()
    # st.write(select_index_num_list)
    return select_index_num_list
    
def equipment_checked_df_ui(equipment,filtered_equipment_df,select_index_num_list):
    equipment_json = {"weapon": "武器", "armor": "防具", "accesory": "装飾"}
    # 重複している行のみ '装備名' と 'レアリティ' を結合
    filtered_equipment_df['count'] = filtered_equipment_df.groupby('装備名')['装備名'].transform('count')
    filtered_equipment_df['装備名_改'] = filtered_equipment_df.apply(
        lambda x: f"{x['装備名']} [{x['レアリティ']}]" if x['count'] > 1 else x['装備名'], axis=1
    )
    
    equipment_checked_rows = filtered_equipment_df[filtered_equipment_df["装備番号"].isin(select_index_num_list)]["装備名_改"].tolist()
    selected_equipment = st.multiselect(f'{equipment_json[equipment]}',equipment_checked_rows,max_selections=1,key=f'selected_{equipment}',placeholder =f'{equipment_json[equipment]}を選択')
    filtered_equipment_df = filtered_equipment_df[filtered_equipment_df["装備番号"].isin(select_index_num_list)].fillna(0)
    final_selected_equipment = []
    if len(selected_equipment) > 0:
        final_selected_equipment = pd.melt(filtered_equipment_df[["体力", "攻撃力", "防御力", "会心率", "命中率", "回避率", "アビリティ"]]).values.tolist()
    # for i in range(len(final_selected_equipment)):
    #     if final_selected_equipment[i][1] !=0:
    #         st.write(f'{final_selected_equipment[i][0]}：{final_selected_equipment[i][1]}')
    return final_selected_equipment

def equipments_status_sum(final_selected_weapon,final_selected_armor,final_selected_accesory):
    status_list = ['体力', '攻撃力', '防御力', '会心率', '命中率', '回避率']
    final_selected_equipment_list = []
    if len(final_selected_weapon)>0:
        final_selected_equipment_list.append(final_selected_weapon)
    if len(final_selected_armor)>0:
        final_selected_equipment_list.append(final_selected_armor)  
    if len(final_selected_accesory)>0:
        final_selected_equipment_list.append(final_selected_accesory)
        
    if len(final_selected_equipment_list)>0:
        for i in range(6):
            status = 0
            for final_selected_equipment in final_selected_equipment_list:
                status += final_selected_equipment[i][1]
            if i < 3:
                st.write(f'{status_list[i]}:{int(status)}')
            else:
                st.write(f'{status_list[i]}:{status}%')
        st.write('## アビリティ')
        for final_selected_equipment in final_selected_equipment_list:
            st.write(f'{final_selected_equipment[6][1]}')

def reload_time():
    """load_log.csv から最新更新日時を取得（文字列: YYYY-MM-DD HH:MM:SS）"""
    path = Path("load_log.csv")
    if not path.exists() or path.stat().st_size == 0:
        return "更新記録なし"

    df = pd.read_csv(path, encoding="utf-8-sig")
    if df.empty or "更新日時" not in df.columns:
        return "更新記録なし"

    # 文字列→datetime（壊れてる行はNaT）
    dt = pd.to_datetime(df["更新日時"], errors="coerce")
    if dt.isna().all():
        return "更新記録なし"

    latest = dt.max()
    return latest.strftime("%Y-%m-%d %H:%M:%S")

def main():
    st.write('# 龍オン装備検索アプリケーション')
    st.write('データ最終更新日時：', reload_time())
    weapon_df, armor_df, accesory_df, category_df = load_data()
    
    with st.sidebar.expander("### 検索フィルタ", expanded=True):
        rarity_select_list = rarity_select_list_ui()
        status_select_list = status_select_list_ui()
        ability_select_list = ability_select_list_ui(category_df)
    equipment_col_select_list = equipment_col_select_ui()

    weapon, armor, accesory = st.tabs(["武器", "防具", "装飾"])
    with weapon:
        filtered_weapon_df = index_filtered_df(weapon_df,rarity_select_list,status_select_list,ability_select_list)
        weapon_select_index_num_list = equipment_checked_df_list('weapon',filtered_weapon_df,equipment_col_select_list )
    with armor:
        filtered_armor_df = index_filtered_df(armor_df,rarity_select_list,status_select_list,ability_select_list)
        armor_select_index_num_list = equipment_checked_df_list('armor',filtered_armor_df,equipment_col_select_list )
    with accesory:
        filtered_accesory_df = index_filtered_df(accesory_df,rarity_select_list,status_select_list,ability_select_list)
        accesory_select_index_num_list = equipment_checked_df_list('accesory',filtered_accesory_df,equipment_col_select_list )
        
    with st.sidebar.expander("### ステータス合算", expanded=True):
        st.write('右のリストからセットしたい装備をcheckしてください')
        final_selected_weapon = equipment_checked_df_ui('weapon',filtered_weapon_df,weapon_select_index_num_list)
        final_selected_armor = equipment_checked_df_ui('armor',filtered_armor_df,armor_select_index_num_list)
        final_selected_accesory = equipment_checked_df_ui('accesory',filtered_accesory_df,accesory_select_index_num_list)
        equipments_status_sum(final_selected_weapon,final_selected_armor,final_selected_accesory)

# エントリーポイント
if __name__ == "__main__":
    main()
