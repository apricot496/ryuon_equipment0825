import sqlite3
import base64
import os

DB_FILE = "equipment.db"
TABLE = "equipment_img_scraping"

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

    # 必要なカラムを追加
    cur.execute(f"PRAGMA table_info({TABLE})")
    columns = [row[1] for row in cur.fetchall()]

    if "IMG_Path" not in columns:
        cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN IMG_Path TEXT")
        print("IMG_Path カラムを追加しました。")

    if "BASE64" not in columns:
        cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN BASE64 TEXT")
        print("BASE64 カラムを追加しました。")

    # IMG_URL を IMG_Path に変換し、BASE64 に保存
    cur.execute(f"SELECT rowid, IMG_URL FROM {TABLE}")
    rows = cur.fetchall()

    for rowid, img_url in rows:
        if not img_url:
            continue

        # プレフィックスを削除して IMG_Path を作成
        if img_url.startswith(PREFIX):
            img_path = img_url.replace(PREFIX, "")
        else:
            img_path = img_url  # 万一プレフィックスが違えばそのまま

        # IMG_Path 更新
        cur.execute(f"UPDATE {TABLE} SET IMG_Path = ? WHERE rowid = ?", (img_path, rowid))

        # ファイルが存在すれば BASE64 に保存
        data_url = path_to_data_url(img_path)
        if data_url:
            cur.execute(f"UPDATE {TABLE} SET BASE64 = ? WHERE rowid = ?", (data_url, rowid))

    conn.commit()
    conn.close()
    print("IMG_Path と BASE64 更新完了")

if __name__ == "__main__":
    update_imgpath_and_base64()
