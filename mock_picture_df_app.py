import streamlit as st
import pandas as pd

df = pd.DataFrame({
    "id": [1, 2],
    "description": ["a の画像", "b の画像"],
    "img": [
        "http://localhost:8890/a.jpg",   # ポート番号に注意
        "http://localhost:8890/b.jpg"
    ]
})

col_cfg = {
    "img": st.column_config.ImageColumn("画像", width="medium")
}

st.dataframe(df, column_config=col_cfg)
