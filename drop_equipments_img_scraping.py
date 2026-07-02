import sqlite3
import os

DB_PATH = "ryuon_equipments.db"

def delete_all_data():
    """テーブルの全データ削除"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM equipments_img_scraping")
    conn.commit()
    conn.close()
    print("✅ 全データを削除しました")
def main():
    delete_all_data()
if __name__ == "__main__":
    main()