import sqlite3
import base64
import os

DB_FILE = "equipment.db"
TABLE = "equipment_img_base64"

# IMG_URL から削除するプレフィックス
PREFIX = "https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/main/"

def path_to_data_url(path):
    """ローカルの画像ファイルを data URL(base64) に変換"""
    if not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    mime = "jpeg" if ext in ["jpg", "jpeg"] else "png"
    with open(path, "rb") as f:
        data = f.read()
    return f"data:image/{mime};base64,{base64.b64encode(data).decode()}"

def update_imgpath_and_base64():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # テーブルが存在するか確認
    cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE}'")
    if not cur.fetchone():
        # テーブルが存在しない場合は作成
        cur.execute(f"""
            CREATE TABLE {TABLE} (
                装備名 TEXT,
                レアリティ TEXT,
                画像名 TEXT,
                IMG_URL TEXT,
                BASE64 TEXT
            )
        """)
        print(f"{TABLE} テーブルを作成しました。")

    # equipment_img_scrapingから装備情報とIMG_URLを取得
    cur.execute("""
        SELECT 装備名, レアリティ, 画像名, IMG_URL 
        FROM equipment_img_scraping
    """)
    rows = cur.fetchall()

    for 装備名, レアリティ, 画像名, img_url in rows:
        if not img_url:
            continue

        # プレフィックスを削除してローカルパスを作成
        if img_url.startswith(PREFIX):
            img_path = img_url.replace(PREFIX, "")
        else:
            img_path = img_url

        # 既にequipment_img_base64に同じ装備名+レアリティのレコードが存在するか確認
        cur.execute(f"""
            SELECT BASE64 FROM {TABLE} 
            WHERE 装備名 = ? AND レアリティ = ?
        """, (装備名, レアリティ))
        existing = cur.fetchone()

        # ファイルが存在すれば BASE64 に変換
        data_url = path_to_data_url(img_path)
        if data_url:
            if existing:
                # 既に存在する場合は更新
                cur.execute(f"""
                    UPDATE {TABLE} 
                    SET 画像名 = ?, IMG_URL = ?, BASE64 = ? 
                    WHERE 装備名 = ? AND レアリティ = ?
                """, (画像名, img_url, data_url, 装備名, レアリティ))
            else:
                # 存在しない場合は新規追加
                cur.execute(f"""
                    INSERT INTO {TABLE} (装備名, レアリティ, 画像名, IMG_URL, BASE64)
                    VALUES (?, ?, ?, ?, ?)
                """, (装備名, レアリティ, 画像名, img_url, data_url))

    conn.commit()
    conn.close()
    print(f"{TABLE} テーブルの更新完了")

if __name__ == "__main__":
    update_imgpath_and_base64()
