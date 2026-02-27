import sqlite3
import pandas as pd

excel_path = "equipment.xlsx"
db_path = "equipment.db"

# Excel読み込み
df = pd.read_excel(excel_path, sheet_name="equipment_img_scraping")

# DB接続
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 既存テーブルを削除して再作成（完全に置き換える）
cur.execute("DROP TABLE IF EXISTS equipment_img_scraping")

# DataFrame から SQL テーブル作成
df.to_sql("equipment_img_scraping", conn, index=False)

conn.commit()
conn.close()

print("SQLite の equipment_img_scraping テーブルを Excel の内容で完全に置き換えました！")
