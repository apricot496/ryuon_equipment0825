import sqlite3
import pandas as pd
import streamlit as st

def load_log():
    """ログテーブルの更新履歴を読み込み"""
    try:
        with sqlite3.connect("equipment.db") as conn:
            # SQLiteでdatetime()に変換してORDER
            query = 'SELECT * FROM load_log ORDER BY datetime("更新日時") DESC;'
            df = pd.read_sql(query, conn)
            
            # 念のためPandas側でもdatetimeに変換
            if "更新日時" in df.columns:
                df["更新日時"] = pd.to_datetime(df["更新日時"], errors="coerce")
                df = df.sort_values("更新日時", ascending=False)
    except Exception as e:
        st.error(f"データベース読み込みエラー: {e}")
        df = pd.DataFrame()
    return df
def load_scraiping():
    """スクレイピング結果の更新履歴を読み込み"""
    try:
        with sqlite3.connect("equipment.db") as conn:
            # SQLiteでdatetime()に変換してORDER
            query = 'SELECT * FROM equipment_img_scraping ORDER BY URL_Number DESC;'
            df = pd.read_sql(query, conn)
            
    except Exception as e:
        st.error(f"データベース読み込みエラー: {e}")
        df = pd.DataFrame()
    return df

def load_equipments_data():
    """SQLite DB からデータを読み込む"""
    conn = sqlite3.connect("equipment.db")
    # スプレッドシートに記載済みのdataを取得
    equipments_list = ["武器", "防具", "装飾"]
    rarelity_order = ['ur', 'ksr', 'ssr']
    df_list = []
    for equipments in equipments_list:
        equipment_df_concat_list = []
        for  rarelity in rarelity_order:
            sheet_name = f"{rarelity}{equipments}"
            df = pd.read_sql(f"""SELECT 
    装備名
    ,装備番号
    , レアリティ
    , アビリティカテゴリ
FROM '{sheet_name}' """, conn)
            df_list.append(df)
    df = pd.concat(df_list, ignore_index=True)
    df = df.replace('', pd.NA)
    df['アビリティカテゴリ'] = df['アビリティカテゴリ'].fillna('アビリティなし')
    # スクレイピング結果を取得
    df_scraping = pd.read_sql("""SELECT
                              装備名
                            , レアリティ
                            , 体力
                            , 攻撃力
                            , 防御力
                            , 会心率
                            , 命中率
                            , 回避率
                            , アビリティ
                            ,URL_Number
                              FROM equipment_img_scraping
                              """, conn)
    df_scraping["URL"] = "https://ryu.sega-online.jp/news/" + df_scraping["URL_Number"].astype(str) + "/"

    left_diff_df = pd.merge(df_scraping ,df[['装備名','装備番号','レアリティ','アビリティカテゴリ']], on=['装備名', 'レアリティ'], how='outer', indicator=True)
    right_diff_df = pd.merge(df ,df_scraping[['装備名','レアリティ','URL_Number','URL']], on=['装備名', 'レアリティ'], how='left', indicator=True)
    diff_df = pd.concat([left_diff_df, right_diff_df])
    diff_df = diff_df[['装備名','装備番号','レアリティ','体力','攻撃力','防御力','会心率','命中率','回避率','アビリティ','アビリティカテゴリ','URL','_merge']]
    diff_df = diff_df[diff_df['_merge'] != 'both'].drop(columns=['_merge'])
    # # アビリティカテゴリ
    # df_category = pd.read_sql("SELECT * FROM 'ability_category'", conn)
    # df_nan = pd.DataFrame({'アビリティカテゴリ分類': ['アビリティなし']})
    # df_category = pd.concat([df_category, df_nan])

    conn.close()
    return diff_df

def main():
    log ,scraiping, diff = st.tabs(["更新履歴", "スクレイピング結果","スクレイピング結果の差分"])
    with log:
        st.subheader("更新履歴")
        df = load_log()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("更新履歴が存在しません。")
    with scraiping:
        st.subheader("スクレイピング結果")  
        df = load_scraiping()
        search_word = st.text_input("装備名で検索", "")

        # 入力がある場合は部分一致でフィルター
        if search_word:
            df = df[df["装備名"].str.contains(search_word, na=False)]
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("更新履歴が存在しません。")
    with diff:
        st.subheader("スクレイピング結果の差分")  
        diff_df = load_equipments_data()
        st.dataframe(diff_df, use_container_width=True)
        st.write("装備番号がNoneのものは、スプレッドシートに未登録の装備です。")
        st.write("装備番号が記載あるものは、スクレイピングが失敗しているまたはHP上に存在しない可能性があります。")


if __name__ == "__main__":
    main()
