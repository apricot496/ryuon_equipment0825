import sqlite3

db_path = "equipment.db"

# 修正したい装備名
name_a = "クララちゃんの蝶ネクタイ"
name_b = "文鳥のブンちゃん(ピンク)"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. それぞれの装備の base64 を取得
cur.execute("SELECT 装備名,BASE64 FROM equipment_img_scraping WHERE 装備名 = ?", (name_a,))
base64_a = cur.fetchone()

cur.execute("SELECT 装備名,BASE64 FROM equipment_img_scraping WHERE 装備名 = ?", (name_b,))
base64_b = cur.fetchone()

if not base64_a or not base64_b:
    print("指定した装備名のデータが見つかりませんでした。")
    conn.close()
    exit()

base64_a = base64_a[1]
base64_b = base64_b[1]

print(base64_a )
# 2. base64 を入れ替える（UPDATE）
cur.execute(
    "UPDATE equipment_img_scraping SET BASE64 = ? WHERE 装備名= ?",
    (base64_b, name_a)
)

cur.execute(
    "UPDATE equipment_img_scraping SET BASE64 = ? WHERE 装備名= ?",
    (base64_a, name_b)
)

conn.commit()
conn.close()

print("BASE64 の入れ替えを修正しました！")
