import sqlite3

DB_FILE = "equipment.db"

def migrate_base64_to_new_table():
    """
    equipment_img_base64テーブルを新規作成し、
    equipment_img_scrapingテーブルからBASE64関連データを移行して、
    古いカラムを削除する。
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # 1. 新しいテーブルを作成
    print("新しいequipment_img_base64テーブルを作成中...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS equipment_img_base64 (
            装備名 TEXT,
            レアリティ TEXT,
            画像名 TEXT,
            IMG_URL TEXT,
            BASE64 TEXT
        )
    """)
    
    # 2. 既存データを移行
    print("データを移行中...")
    cur.execute("""
        INSERT INTO equipment_img_base64 (装備名, レアリティ, 画像名, IMG_URL, BASE64)
        SELECT 装備名, レアリティ, 画像名, IMG_URL, BASE64
        FROM equipment_img_scraping
        WHERE BASE64 IS NOT NULL
    """)
    
    # 3. equipment_img_scrapingテーブルを再作成してBASE64とIMG_Pathカラムを削除
    print("equipment_img_scrapingテーブルを再構築中...")
    
    # 既存データを一時テーブルに保存
    cur.execute("""
        CREATE TABLE equipment_img_scraping_temp AS
        SELECT 装備名, レアリティ, 画像名, 体力, 攻撃力, 防御力, 会心率, 回避率, 命中率, アビリティ, 新規フラグ, URL_Number, IMG_URL
        FROM equipment_img_scraping
    """)
    
    # 古いテーブルを削除
    cur.execute("DROP TABLE equipment_img_scraping")
    
    # 新しい構造でテーブルを再作成
    cur.execute("""
        CREATE TABLE equipment_img_scraping (
            装備名 TEXT,
            レアリティ TEXT,
            画像名 TEXT,
            体力 TEXT,
            攻撃力 TEXT,
            防御力 TEXT,
            会心率 TEXT,
            回避率 TEXT,
            命中率 TEXT,
            アビリティ TEXT,
            新規フラグ TEXT,
            URL_Number TEXT,
            IMG_URL TEXT
        )
    """)
    
    # データを戻す
    cur.execute("""
        INSERT INTO equipment_img_scraping
        SELECT * FROM equipment_img_scraping_temp
    """)
    
    # 一時テーブルを削除
    cur.execute("DROP TABLE equipment_img_scraping_temp")
    
    conn.commit()
    
    # 4. 結果を確認
    cur.execute("SELECT COUNT(*) FROM equipment_img_base64")
    count = cur.fetchone()[0]
    print(f"✓ equipment_img_base64テーブルに{count}件のレコードを移行しました")
    
    cur.execute("PRAGMA table_info(equipment_img_scraping)")
    columns = [row[1] for row in cur.fetchall()]
    print(f"✓ equipment_img_scrapingテーブルの新しいカラム: {', '.join(columns)}")
    
    conn.close()
    print("\nマイグレーション完了!")

if __name__ == "__main__":
    migrate_base64_to_new_table()
