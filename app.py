import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2 import service_account

# ページのタイトルとアイコンを設定
st.set_page_config(page_title="Ryuon_Apricot_Equipmentdata")

@st.cache_resource
def load_data():
    # 認証情報の設定
    #scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = service_account.Credentials.from_service_account_info( st.secrets["gcp_service_account"], scopes=[ "https://www.googleapis.com/auth/spreadsheets", ],
)
    equipments_list = ['武器','防具','装飾']
    df_list =[]
    
    gc = gspread.authorize(credentials)
    for sheet_name in equipments_list:
        # スプレッドシートを開く
        spreadsheet_key = st.secrets['spreadsheet_key_name']
        worksheet_ur = gc.open_by_key(spreadsheet_key).worksheet('ur'+sheet_name)
        worksheet_ksr = gc.open_by_key(spreadsheet_key).worksheet('ksr'+sheet_name)
        worksheet_ssr = gc.open_by_key(spreadsheet_key).worksheet('ssr'+sheet_name)

        # シートデータの読み込み
        data_ur = worksheet_ur.get_all_records()
        data_ksr = worksheet_ksr.get_all_records()
        data_ssr = worksheet_ssr.get_all_records()

        # 辞書のリストからDataFrameに変換
        df_ur = pd.DataFrame(data_ur)
        df_ksr = pd.DataFrame(data_ksr)
        df_ssr = pd.DataFrame(data_ssr)
        
        df = pd.concat([df_ur, df_ksr, df_ssr],ignore_index=True)
        df =df.replace('',np.nan)
        df['check'] = False
        # チェック列を一番左に移動
        columns = ['check'] + [col for col in df.columns if col != 'check']
        df = df[columns]
        df['アビリティカテゴリ'] = df['アビリティカテゴリ'].fillna('アビリティなし')
        # シートデータを結合して1つのDataFrameにする
        df_list.append(df)
    
    worksheet_category = gc.open_by_key(spreadsheet_key).worksheet('ability-category')
    data_category = worksheet_category.get_all_records()
    df_category = pd.DataFrame(data_category)
    df_nan = pd.DataFrame({'アビリティカテゴリ分類': ['アビリティなし']})
    df_category = pd.concat([df_category,df_nan])
    return df_list[0],df_list[1],df_list[2],df_category

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
        label=None,
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
        label=None,
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
    ability_select_list = st.multiselect(label='',options = ability_name_list,label_visibility= 'collapsed')
    
    if len(ability_select_list) == 0:
        ability_select_list = ability_name_list
    return ability_select_list

def equipment_col_select_ui():
    equipment_col_list = ['レアリティ', '体力', '攻撃力', '防御力', '会心率', '命中率', '回避率', 'アビリティ']
    
    # 初期状態のセッション設定
    if "col_state" not in st.session_state:
        st.session_state["col_state"] = equipment_col_list

    # UIのレイアウト
    cols = st.columns([2, 1, 1])
    with cols[0]:
        st.write("### 表示項目")
    with cols[1]:
        if st.button('全選択', key='all_select_col_button'):
            st.session_state["col_state"] = equipment_col_list
    with cols[2]:
        if st.button('リセット', key='all_reset_col_button'):
            st.session_state["col_state"] = []

    # `st.multiselect` の選択項目をセッション状態で管理
    equipment_col_select_list = st.multiselect(
        label='',
        options=equipment_col_list,
        default=st.session_state["col_state"],
        label_visibility='collapsed'
    )
    # セッション状態を更新
    if set(equipment_col_select_list) != set(st.session_state["col_state"]):
        st.session_state["col_state"] = equipment_col_select_list

    return st.session_state["col_state"]


def equipment_col_select_ui():
    equipment_col_list = ['レアリティ', '体力', '攻撃力', '防御力', '会心率', '命中率', '回避率', 'アビリティ']
    st.write("### 表示項目")
    # `st.multiselect` の選択項目をセッション状態で管理
    equipment_col_select_list = st.multiselect(
        label='',
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
    
    equipment_df = pd.concat([filtered_equipment_df[['check', '装備名']], filtered_equipment_df[equipment_col_select_list]],axis=1)
    equipment_df["check"] = equipment_df.index.isin(st.session_state[session_key])
    equipment_df = st.data_editor(equipment_df,disabled=(col for col in equipment_col_select_list + ["装備名"]),key=f"{equipment}_df")
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


def main():
    st.write('# 龍オン装備検索アプリケーション')
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
