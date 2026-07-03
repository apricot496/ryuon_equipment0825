"""
一回限りの移行スクリプト: 旧スキーマ → confirmed_* スキーマ

実行内容:
  DB:
    1. non_check_equipments → unconfirmed_equipments にリネーム
    2. 旧確認済みテーブル (ur武器 / ksr武器 / ssr武器 / ... 9件) を削除
    3. mart_equipments を削除（次回 create_mart_equipments.py で再構築）
  SS:
    4. non_check_equipments シート → unconfirmed_equipments にリネーム
"""

import os
import sqlite3
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

DB_FILE = "equipment.db"

OLD_CONFIRMED_TABLES = [
    "ur武器", "ur防具", "ur装飾",
    "ksr武器", "ksr防具", "ksr装飾",
    "ssr武器", "ssr防具", "ssr装飾",
]

OLD_NON_CHECK = "non_check_equipments"
NEW_UNCONFIRMED = "unconfirmed_equipments"


def migrate_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # 1. non_check_equipments → unconfirmed_equipments
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (OLD_NON_CHECK,)
    )
    if cur.fetchone():
        cur.execute(f'ALTER TABLE "{OLD_NON_CHECK}" RENAME TO "{NEW_UNCONFIRMED}"')
        print(f"✅ DB: {OLD_NON_CHECK} → {NEW_UNCONFIRMED} にリネームしました")
    else:
        print(f"⚠️  DB: {OLD_NON_CHECK} テーブルが存在しません（スキップ）")

    # 2. 旧確認済みテーブルを削除
    for table in OLD_CONFIRMED_TABLES:
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        if cur.fetchone():
            cur.execute(f'DROP TABLE "{table}"')
            print(f"🗑️  DB: {table} を削除しました")
        else:
            print(f"⚠️  DB: {table} は存在しません（スキップ）")

    # 3. mart_equipments を削除（要再構築）
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mart_equipments'"
    )
    if cur.fetchone():
        cur.execute("DROP TABLE mart_equipments")
        print("🗑️  DB: mart_equipments を削除しました（create_mart_equipments.py で再構築してください）")

    conn.commit()
    conn.close()
    print("\nDB 移行完了")


def migrate_ss():
    load_dotenv()
    spreadsheet_key = os.getenv("SPREADSHEET_KEY_NAME")
    creds_info = {
        "type": os.getenv("GCP_TYPE"),
        "project_id": os.getenv("GCP_PROJECT_ID"),
        "private_key_id": os.getenv("GCP_PRIVATE_KEY_ID"),
        "private_key": os.getenv("GCP_PRIVATE_KEY").replace("\\n", "\n"),
        "client_email": os.getenv("GCP_CLIENT_EMAIL"),
        "client_id": os.getenv("GCP_CLIENT_ID"),
        "auth_uri": os.getenv("GCP_AUTH_URI"),
        "token_uri": os.getenv("GCP_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GCP_AUTH_PROVIDER_CERT_URL"),
        "client_x509_cert_url": os.getenv("GCP_CLIENT_CERT_URL"),
        "universe_domain": os.getenv("GCP_UNIVERSE_DOMAIN"),
    }

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(spreadsheet_key)

    # 4. non_check_equipments → unconfirmed_equipments
    try:
        ws = spreadsheet.worksheet(OLD_NON_CHECK)
        ws.update_title(NEW_UNCONFIRMED)
        print(f"✅ SS: {OLD_NON_CHECK} → {NEW_UNCONFIRMED} にリネームしました")
    except gspread.WorksheetNotFound:
        print(f"⚠️  SS: {OLD_NON_CHECK} シートが見つかりません（スキップ）")

    print("\nSS 移行完了")


if __name__ == "__main__":
    print("=== DB 移行 ===")
    migrate_db()
    print("\n=== SS 移行 ===")
    migrate_ss()
    print("\n移行完了。次に create_mart_equipments.py を実行してください。")
