import streamlit as st
import pandas as pd

df = pd.DataFrame({
    "id": [1, 2],
    "description": ["a の画像", "b の画像"],
    "img": [
        "https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/main/static/カムロップステッキ_SSR.png", 
        "https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/main/static/カムロップヘルム_SSR.png"
    ]
})

col_cfg = {
    "img": st.column_config.ImageColumn("画像", width="medium")
}

st.dataframe(df, column_config=col_cfg)
