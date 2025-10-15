import sqlite3

DB_PATH = "equipment.db"

# DB接続
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""CREATE TABLE new_eqipment_img_scraping AS
WITH 
max_num_index AS (
    SELECT 
    "装備名"
    , "レアリティ"
    , "画像名"
    , "体力"
    , "攻撃力"
    , "防御力"
    , "会心率"
    , "回避率"
    , "命中率"
    , "アビリティ"
    , "新規フラグ"
    , "URL_Number"
    , "IMG_URL"
    , "IMG_Path"
    , "BASE64"
    FROM eqipment_img_scraping
    WHERE "URL_Number" = (SELECT MAX("URL_Number") FROM eqipment_img_scraping)
    ORDER BY "URL_Number" DESC
    limit 1
),
re_eqipment_img_scraping AS (
    SELECT

    "装備名"
    , "レアリティ"
    , MIN("画像名") AS "画像名"
    , MIN("体力") AS "体力"
    , MIN("攻撃力") AS "攻撃力"
    , MIN("防御力") AS "防御力"
    , MIN("会心率") AS "会心率"
    , MIN("回避率") AS "回避率"
    , MIN("命中率") AS "命中率"
    , MIN("アビリティ") AS "アビリティ"
    , MIN("新規フラグ") AS "新規フラグ"
    , MIN("URL_Number")AS "URL_Number"
    , MIN("IMG_URL") AS "IMG_URL"
    , MIN("IMG_Path") AS "IMG_Path"
    , MIN("BASE64") AS "BASE64"
    FROM eqipment_img_scraping
    WHERE "装備名" IS NOT NULL
    GROUP BY "装備名", "レアリティ"
    ),
latest_numbered_equipment_table AS (
        SELECT * FROM re_eqipment_img_scraping
        UNION ALL
        SELECT * FROM max_num_index
    ),
latest_drop_equipment_table AS(
    SELECT
    "装備名"
    , "レアリティ"
    , MIN("画像名") AS "画像名"
    , MIN("体力") AS "体力"
    , MIN("攻撃力") AS "攻撃力"
    , MIN("防御力") AS "防御力"
    , MIN("会心率") AS "会心率"
    , MIN("回避率") AS "回避率"
    , MIN("命中率") AS "命中率"
    , MIN("アビリティ") AS "アビリティ"
    , MIN("新規フラグ") AS "新規フラグ"
    , MIN("URL_Number")AS "URL_Number"
    , MIN("IMG_URL") AS "IMG_URL"
    , MIN("IMG_Path") AS "IMG_Path"
    , MIN("BASE64") AS "BASE64"
FROM latest_numbered_equipment_table
GROUP BY "装備名", "レアリティ"
ORDER BY "URL_Number"
)
SELECT * FROM latest_drop_equipment_table;
            """)

# 元テーブルを置き換えたい場合
cur.execute("DROP TABLE eqipment_img_scraping")
cur.execute("ALTER TABLE new_eqipment_img_scraping RENAME TO eqipment_img_scraping")

# VACUUMで空き領域を解放
cur.execute("VACUUM;")

conn.commit()
conn.close()
