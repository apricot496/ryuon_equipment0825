import sqlite3

DB_PATH = "equipment.db"

# DB接続
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE new_eqipment_img_scraping AS
    WITH 
    max_num_index AS (
        SELECT *
        FROM eqipment_img_scraping
        WHERE URL_Number = (SELECT MAX(URL_Number) FROM eqipment_img_scraping)
    ),
    re_eqipment_img_scraping AS (
        SELECT *
        FROM eqipment_img_scraping
        WHERE 装備名 IS NOT NULL
    )
    SELECT * FROM re_eqipment_img_scraping
    UNION ALL
    SELECT * FROM max_num_index WHERE 装備名 IS NULL
""")

# 元テーブルを置き換えたい場合
cur.execute("DROP TABLE eqipment_img_scraping")
cur.execute("ALTER TABLE new_eqipment_img_scraping RENAME TO eqipment_img_scraping")
conn.commit()
conn.close()
