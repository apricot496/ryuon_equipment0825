import sqlite3
import os

DB_PATH = "equipment.db"

def delete_all_data():
    """テーブルの全データ削除"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM eqipment_img_scraping")
    conn.commit()
    conn.close()
    print("✅ 全データを削除しました")
def main():
    delete_all_data()
if __name__ == "__main__":
    main()