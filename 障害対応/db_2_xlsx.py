import sqlite3
import pandas as pd

# --- 入力DBファイル名 ---
db_path = "equipment.db"

# --- 出力Excelファイル名 ---
excel_output = "equipment.xlsx"

# SQLiteへ接続
conn = sqlite3.connect(db_path)

# テーブル一覧を取得
query = "SELECT name FROM sqlite_master WHERE type='table';"
tables = pd.read_sql(query, conn)

# ExcelWriterを使って複数シートに出力
with pd.ExcelWriter(excel_output, engine='openpyxl') as writer:
    for table_name in tables['name']:
        print(f"Exporting table: {table_name}")
        df = pd.read_sql(f"SELECT * FROM {table_name};", conn)
        df.to_excel(writer, sheet_name=table_name, index=False)

conn.close()

print("📘 Excel出力が完了しました:", excel_output)
