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
            query = 'SELECT * FROM eqipment_img_scraping ORDER BY URL_Number DESC;'
            df = pd.read_sql(query, conn)
            
    except Exception as e:
        st.error(f"データベース読み込みエラー: {e}")
        df = pd.DataFrame()
    return df

def main():
    log ,scraiping = st.tabs(["更新履歴", "スクレイピング結果"])
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
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("更新履歴が存在しません。")

if __name__ == "__main__":
    main()
