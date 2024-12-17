import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def load_data():
    json_keyfile = 'ryuon-equipment-38a59fa0f789.json'
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(json_keyfile, scope)
    gc = gspread.authorize(credentials)

    # スプレッドシートを開く
    spreadsheet_key = '1LZiE6wf8VTwFoVxeEBTx3OXOKx6vQA5IaItE7NQYZTs'
    worksheet_ksr_weapon = gc.open_by_key(spreadsheet_key).worksheet('ksr武器')
    worksheet_ssr_weapon = gc.open_by_key(spreadsheet_key).worksheet('ssr武器')
    worksheet_ksr_armor = gc.open_by_key(spreadsheet_key).worksheet('ksr防具')
    worksheet_ssr_armor = gc.open_by_key(spreadsheet_key).worksheet('ssr防具')
    worksheet_ksr_accesary = gc.open_by_key(spreadsheet_key).worksheet('ksr装飾')
    worksheet_ssr_accesary = gc.open_by_key(spreadsheet_key).worksheet('ssr装飾')
    worksheet_category = gc.open_by_key(spreadsheet_key).worksheet('ability-category')

    # シートデータの読み込み
    data_ksr_weapon = worksheet_ksr_weapon.get_all_records()
    data_ssr_weapon = worksheet_ssr_weapon.get_all_records()
    data_ksr_armor = worksheet_ksr_armor.get_all_records()
    data_ssr_armor = worksheet_ssr_armor.get_all_records()
    data_ksr_accesary = worksheet_ksr_accesary.get_all_records()
    data_ssr_accesary = worksheet_ssr_accesary.get_all_records()

    data_category = worksheet_category.get_all_records()

    # 辞書のリストからDataFrameに変換
    df_ksr_weapon = pd.DataFrame(data_ksr_weapon)
    df_ssr_weapon = pd.DataFrame(data_ssr_weapon)
    df_ksr_armor = pd.DataFrame(data_ksr_armor)
    df_ssr_armor = pd.DataFrame(data_ssr_armor)
    df_ksr_accesary = pd.DataFrame(data_ksr_accesary)
    df_ssr_accesary = pd.DataFrame(data_ssr_accesary)
    df_category = pd.DataFrame(data_category)

    # DataFrameを辞書にする
    df_dict = {
        'ksr_weapon': df_ksr_weapon,
        'ssr_weapon': df_ssr_weapon,
        'ksr_armor': df_ksr_armor,
        'ssr_armor': df_ssr_armor,
        'ksr_accesary': df_ksr_accesary,
        'ssr_accesary': df_ssr_accesary,
        'ability-category': df_category
    }
    
    return df_dict

def save_as_csv(df_dict):
    for sheet_name, df in df_dict.items():
        # CSVファイル名を指定
        csv_filename = f"{sheet_name}.csv"
        
        # DataFrameをCSVファイルとして保存
        df.to_csv('./sobi/' + csv_filename, index=False)
        print(f"{csv_filename} に保存しました。")

if __name__ == "__main__":
    # データを読み込む
    df_dict = load_data()

    # CSVに保存する
    save_as_csv(df_dict)
