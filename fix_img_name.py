import sqlite3
import os
import csv
import shutil

DB_PATH = "equipment.db"
CSV_PATH = "fix_name_list.csv"
STATIC_DIR = "static"

BASE_URL = "https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/main/static/"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        old_name = row["修正前_装備名"]
        old_rarity = row["修正前_レアリティ"]
        new_name = row["修正後_装備名"]
        new_rarity = row["修正後_レアリティ"]

        old_img = f"{old_name}_{old_rarity}.png"
        new_img = f"{new_name}_{new_rarity}.png"

        new_url = BASE_URL + new_img

        print(f"[更新対象] {old_name}({old_rarity}) → {new_name}({new_rarity})")

        # --- DB更新 ---
        cur.execute("""
            UPDATE eqipment_img_scraping
            SET 装備名 = ?, レアリティ = ?, 画像名 = ?, IMG_URL = ?
            WHERE 装備名 = ? AND レアリティ = ?
        """, (
            new_name, new_rarity, new_img, new_url,
            old_name, old_rarity
        ))

        # --- 画像ファイルリネーム ---
        old_path = os.path.join(STATIC_DIR, old_img)
        new_path = os.path.join(STATIC_DIR, new_img)
        if os.path.exists(old_path):
            shutil.move(old_path, new_path)
            print(f"  画像リネーム済み: {old_img} → {new_img}")
        else:
            print(f"  ⚠ ファイル未発見: {old_img}")

conn.commit()
conn.close()
print("DBと画像ファイルの更新が完了しました。")
