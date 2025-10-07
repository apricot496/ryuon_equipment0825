import streamlit as st
import pandas as pd

df = pd.DataFrame({
    "id": [1, 2],
    "description": ["a の画像", "b の画像"],
    "img": [
        "https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/blob/issue_006/static/a.jpg",   # ポート番号に注意
        "https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/blob/issue_006/static/b.jpg"
    ]
})

col_cfg = {
    "img": st.column_config.ImageColumn("画像", width="medium")
}

st.dataframe(df, column_config=col_cfg)
