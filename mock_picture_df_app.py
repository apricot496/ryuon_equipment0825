import streamlit as st
import pandas as pd
import sqlite3

DB_PATH = "equipment.db"

# DB接続
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql(f"SELECT * FROM equipment_img_scraping", conn)
conn.close()

col_cfg = {
    "IMG_URL": st.column_config.ImageColumn("画像", width="medium")
}

st.dataframe(df, column_config=col_cfg)
