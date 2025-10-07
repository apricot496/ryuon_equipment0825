import sqlite3

DB_PATH = "equipment.db"

# DB接続
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# IMG_URL の文字列を置換
cur.execute("""
    UPDATE eqipment_img_scraping
    SET IMG_URL = REPLACE(
        IMG_URL,
        'https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/issue_006/',
        'https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/main/'
    )
""")

# コミットして保存
conn.commit()
conn.close()

print("IMG_URL を issue_006 → main に置換しました。")
