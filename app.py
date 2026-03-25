import streamlit as st
import pandas as pd
import sqlite3
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ページのタイトルとアイコンを設定
st.set_page_config(page_title="Ryuon_Apricot_Equipmentdata")

DB_FILE = "equipment.db"
SCORE_DB_FILE = "equipments_mart_score.db"
EVALUATION_SHEETS_IMAGE_DIR = Path("evaluation_sheets/images")


def _extract_probability_percent(text: str) -> float | None:
    if not isinstance(text, str):
        return None
    normalized = text.replace('％', '%')
    bracket_match = re.search(r'(\d+)\[(\d+)\]%の確率', normalized)
    if bracket_match:
        return float(max(int(bracket_match.group(1)), int(bracket_match.group(2))))
    match = re.search(r'(\d+(?:\.\d+)?)%の確率', normalized)
    if match:
        return float(match.group(1))
    return None


def _get_latest_mart_score_table(conn: sqlite3.Connection) -> str | None:
    """score DB から最新の *_equipments_mart_score テーブル名を取得"""
    query = """
        SELECT name
        FROM scoredb.sqlite_master
        WHERE type = 'table'
          AND name LIKE '%_equipments_mart_score'
        ORDER BY name DESC
        LIMIT 1
    """
    row = conn.execute(query).fetchone()
    if not row:
        return None
    return row[0]

@st.cache_data(ttl=3600)
def load_data(include_images: bool = False):
    """SQLite DB からデータを読み込む"""
    conn = sqlite3.connect(DB_FILE)
    conn.execute(f"ATTACH DATABASE '{SCORE_DB_FILE}' AS scoredb")

    score_table = _get_latest_mart_score_table(conn)

    equipments_list = ["武器", "防具", "装飾"]
    df_list = []

    for equipments in equipments_list:
        image_select = "e.IMG_URL AS 画像" if include_images else "NULL AS 画像"
        image_join = """
LEFT JOIN equipment_img_base64 AS e
ON m.装備名 = e.装備名 AND m.レアリティ = e.レアリティ
""" if include_images else ""

        base_query = f"""
SELECT 
    m.装備名
    , {image_select}
    , m.装備番号
    , m.レアリティ
    , m.体力
    , m.攻撃力
    , m.防御力
    , m.会心率
    , m.命中率
    , m.回避率
    , 0.0 AS ステータススコア
    , m.アビリティ
    , m.アビリティカテゴリ
    , m.アビリティスコア
    , m.発動条件
    , NULL AS アビリティ_抽出効果値
    , NULL AS アビリティ_発動条件
FROM mart_equipments_master AS m
{image_join}
WHERE m.装備種類 = '{equipments}'
"""

        if score_table:
            score_image_join = """
LEFT JOIN equipment_img_base64 AS e
ON s.装備名 = e.装備名 AND s.レアリティ = e.レアリティ
""" if include_images else ""
            query = f"""
SELECT
    s.装備名
    , {image_select.replace('m.', 's.')}
    , s.装備番号
    , s.レアリティ
    , s.体力
    , s.攻撃力
    , s.防御力
    , s.会心率
    , s.命中率
    , s.回避率
    , s.ステータススコア
    , s.アビリティ
    , s.アビリティカテゴリ
    , s.アビリティスコア
    , s.発動条件
    , s.アビリティ_抽出効果値
    , s.アビリティ_発動条件
FROM scoredb."{score_table}" AS s
{score_image_join}
WHERE s.装備種類 = '{equipments}'
"""
            df = pd.read_sql(query, conn)
        else:
            df = pd.read_sql(base_query, conn)
        
        df = df.sort_values('装備番号', ignore_index=True)
        df = df.replace('', pd.NA)
        if 'ステータススコア' not in df.columns:
            df['ステータススコア'] = 0.0
        if 'アビリティスコア' not in df.columns:
            df['アビリティスコア'] = 0.0
        if '発動条件' not in df.columns:
            df['発動条件'] = ''
        if 'アビリティ_抽出効果値' not in df.columns:
            df['アビリティ_抽出効果値'] = None
        if 'アビリティ_発動条件' not in df.columns:
            df['アビリティ_発動条件'] = None

        # デフォルト: アビリティ_抽出効果値 -> 効果量
        df.rename(columns={'アビリティ_抽出効果値': '効果量'}, inplace=True)

        # 状態異常付与: アビリティ文中の発動確率(%)を効果量として採用
        status_abnormal_mask = df['アビリティカテゴリ'] == '状態異常付与'
        abnormal_probability = df.loc[status_abnormal_mask, 'アビリティ'].apply(_extract_probability_percent)
        df.loc[status_abnormal_mask, '効果量'] = abnormal_probability

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
    # アビリティ名のリストを作成
    ability_name_list = category_df['アビリティカテゴリ分類'].unique()
    # # Nanを削除
    # ability_name_list = ability_name_list[1:]
    #複数選択
    ability_select_list = st.multiselect(label='アビリティ',options = ability_name_list,label_visibility= 'collapsed')
    
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
    equipment_col_list = ['レアリティ', '体力', '攻撃力', '防御力', '会心率', '命中率', '回避率', 'アビリティ', 'ステータススコア', 'アビリティスコア', '発動条件', '効果量']
    default_cols = ['レアリティ', '体力', '攻撃力', '防御力', '会心率', '命中率', '回避率', 'アビリティ', 'ステータススコア', 'アビリティスコア', '発動条件', '効果量']
    # `st.multiselect` の選択項目をセッション状態で管理
    equipment_col_select_list = st.multiselect(
        label='表示項目',
        options=equipment_col_list,
        default=default_cols,
        label_visibility='collapsed'
    )
    return equipment_col_select_list


def score_filter_ui():
    status_score_min = st.slider(
        label='ステータススコア（以上）',
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
    )
    ability_score_min = st.slider(
        label='アビリティスコア（以上）',
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
    )
    condition_options = ['常時', '敵依存', '(空欄)']
    condition_select_list = st.multiselect(
        label='発動条件',
        options=condition_options,
        default=condition_options,
    )
    return status_score_min, ability_score_min, condition_select_list


def index_filtered_df(df,rarity_select_list,status_select_list,ability_select_list,status_score_min,ability_score_min,condition_select_list):
    df_col = df.copy()
    df = df[df['レアリティ'].isin(rarity_select_list)]
    for status in status_select_list:
        df = df[df[status].notnull() == True]
    df = df[df['アビリティカテゴリ'].apply(lambda x: any(ab in x for ab in ability_select_list) if pd.notnull(x) else False)]

    # ステータススコア（以上）
    df = df[df['ステータススコア'].fillna(0) >= status_score_min]

    # アビリティスコア（以上）
    df = df[df['アビリティスコア'].fillna(0) >= ability_score_min]

    # 発動条件
    if condition_select_list:
        condition_series = df['発動条件'].fillna('')
        cond_mask = pd.Series(False, index=df.index)
        if '常時' in condition_select_list:
            cond_mask = cond_mask | (condition_series == '常時')
        if '敵依存' in condition_select_list:
            cond_mask = cond_mask | (condition_series == '敵依存')
        if '(空欄)' in condition_select_list:
            cond_mask = cond_mask | (condition_series == '')
        df = df[cond_mask]

    if df.shape[1]==0:
        df = pd.DataFrame(columns=df_col.columns)
    return df

def equipment_checked_df_list(equipment, filtered_equipment_df, equipment_col_select_list, show_image):
    session_key = f"{equipment}_checked_rows"
    if session_key not in st.session_state:
        st.session_state[session_key] = []
    # 画像の読み込み
    col_cfg = {
        "画像": st.column_config.ImageColumn("画像"),
    }
    
    selected_cols = [col for col in equipment_col_select_list if col not in ['check', '装備名', '画像']]
    base_cols = ['check', '装備名']
    if show_image:
        base_cols.append('画像')
    display_cols = base_cols + selected_cols

    equipment_df = filtered_equipment_df[display_cols].copy()
    equipment_df["check"] = equipment_df.index.isin(st.session_state[session_key])
    disabled_cols = [col for col in equipment_df.columns if col != 'check']
    equipment_df = st.data_editor(equipment_df,disabled=disabled_cols,key=f"{equipment}_df", column_config=col_cfg)
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


def _guess_mime_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == '.png':
        return 'image/png'
    if suffix in ['.jpg', '.jpeg']:
        return 'image/jpeg'
    if suffix == '.webp':
        return 'image/webp'
    if suffix == '.html':
        return 'text/html'
    return 'application/octet-stream'


def evaluation_sheet_download_ui():
    if not EVALUATION_SHEETS_IMAGE_DIR.exists():
        st.caption('evaluation_sheets/images が存在しません')
        return

    target_files = sorted(
        [p for p in EVALUATION_SHEETS_IMAGE_DIR.iterdir() if p.is_file()],
        key=lambda p: p.name,
        reverse=True,
    )

    if not target_files:
        st.caption('ダウンロード対象の評価シートがありません')
        return

    st.caption('ファイル名の降順で表示')
    options = [p.name for p in target_files]
    selected_files = st.multiselect(
        label='評価シートを選択',
        options=options,
        default=[],
        placeholder='ダウンロードしたい評価シートを選択',
    )

    for filename in selected_files:
        file_path = EVALUATION_SHEETS_IMAGE_DIR / filename
        if not file_path.exists():
            continue
        st.download_button(
            label=f'DL: {filename}',
            data=file_path.read_bytes(),
            file_name=filename,
            mime=_guess_mime_type(file_path),
            key=f'dl_eval_sheet_{filename}',
        )

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
    show_image = st.toggle('画像表示', value=False)
    weapon_df, armor_df, accesory_df, category_df = load_data(include_images=show_image)
    
    with st.sidebar.expander("### 検索フィルタ", expanded=True):
        rarity_select_list = rarity_select_list_ui()
        status_select_list = status_select_list_ui()
        ability_select_list = ability_select_list_ui(category_df)
        status_score_min, ability_score_min, condition_select_list = score_filter_ui()
    equipment_col_select_list = equipment_col_select_ui()

    weapon, armor, accesory = st.tabs(["武器", "防具", "装飾"])
    with weapon:
        filtered_weapon_df = index_filtered_df(weapon_df,rarity_select_list,status_select_list,ability_select_list,status_score_min,ability_score_min,condition_select_list)
        weapon_select_index_num_list = equipment_checked_df_list('weapon',filtered_weapon_df,equipment_col_select_list,show_image)
    with armor:
        filtered_armor_df = index_filtered_df(armor_df,rarity_select_list,status_select_list,ability_select_list,status_score_min,ability_score_min,condition_select_list)
        armor_select_index_num_list = equipment_checked_df_list('armor',filtered_armor_df,equipment_col_select_list,show_image)
    with accesory:
        filtered_accesory_df = index_filtered_df(accesory_df,rarity_select_list,status_select_list,ability_select_list,status_score_min,ability_score_min,condition_select_list)
        accesory_select_index_num_list = equipment_checked_df_list('accesory',filtered_accesory_df,equipment_col_select_list,show_image)
        
    with st.sidebar.expander("### ステータス合算", expanded=True):
        st.write('右のリストからセットしたい装備をcheckしてください')
        final_selected_weapon = equipment_checked_df_ui('weapon',filtered_weapon_df,weapon_select_index_num_list)
        final_selected_armor = equipment_checked_df_ui('armor',filtered_armor_df,armor_select_index_num_list)
        final_selected_accesory = equipment_checked_df_ui('accesory',filtered_accesory_df,accesory_select_index_num_list)
        equipments_status_sum(final_selected_weapon,final_selected_armor,final_selected_accesory)

    with st.sidebar.expander("### 評価シートDL", expanded=True):
        evaluation_sheet_download_ui()

# エントリーポイント
if __name__ == "__main__":
    main()
