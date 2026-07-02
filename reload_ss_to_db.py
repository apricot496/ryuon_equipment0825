import argparse
import os
import json
import sqlite3
import pandas as pd
import gspread
from google.oauth2 import service_account
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import csv

DB_FILE = "equipment.db"
CONFIRMED_SHEET_NAMES = [
    "ur武器", "ur防具", "ur装飾",
    "ksr武器", "ksr防具", "ksr装飾",
    "ssr武器", "ssr防具", "ssr装飾",
    "ability_category",
]
SHEET_NAMES = CONFIRMED_SHEET_NAMES + ["non_check_equipments"]
JST = timezone(timedelta(hours=9))

def load_credentials_and_key():
    """ローカルなら .env から、GitHub Actions なら Secrets から読み込む"""
    if os.getenv("GITHUB_ACTIONS") == "true":
        spreadsheet_key = os.environ["SPREADSHEET_KEY_NAME"]
        creds_info = {
            "type": os.environ["GCP_TYPE"],
            "project_id": os.environ["GCP_PROJECT_ID"],
            "private_key_id": os.environ["GCP_PRIVATE_KEY_ID"],
            "private_key": os.environ["GCP_PRIVATE_KEY"].replace("\\n", "\n"),
            "client_email": os.environ["GCP_CLIENT_EMAIL"],
            "client_id": os.environ["GCP_CLIENT_ID"],
            "auth_uri": os.environ["GCP_AUTH_URI"],
            "token_uri": os.environ["GCP_TOKEN_URI"],
            "auth_provider_x509_cert_url": os.environ["GCP_AUTH_PROVIDER_CERT_URL"],
            "client_x509_cert_url": os.environ["GCP_CLIENT_CERT_URL"],
            "universe_domain": os.environ["GCP_UNIVERSE_DOMAIN"],
        }
    else:
        # ローカル環境
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

    return creds_info, spreadsheet_key

def cast_dataframe(sheet_name: str, df: pd.DataFrame) -> pd.DataFrame:
    """列の型変換。int列に小数が混じっていたらエラー"""
    if sheet_name != "ability_category":
        # int列
        for col in ["体力", "攻撃力", "防御力"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                if (df[col].dropna() % 1 != 0).any():
                    raise ValueError(f"{sheet_name} の {col} 列に小数が含まれています。修正してください。")
                df[col] = df[col].astype("Int64")

        # float列
        for col in ["会心率", "回避率", "命中率"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(1)

    return df

def save_to_db(sheet_name: str, df: pd.DataFrame, conn: sqlite3.Connection):
    # ヘッダー行がデータとして混入している場合は除去（装備名列が列名自身と一致する行）
    if "装備名" in df.columns:
        df = df[df["装備名"] != "装備名"]
    df.to_sql(sheet_name, conn, if_exists="replace", index=False)
    print(f"✅ {sheet_name} を保存しました")

# def insert_log(conn, row_counts: dict, commit_message: str):
#     now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
#     columns = ["更新日時", "コミットメッセージ"] + SHEET_NAMES
#     values = [now, commit_message] + [row_counts.get(sheet, 0) for sheet in SHEET_NAMES]

#     # カラム名をハイフン→アンダースコアに変換
#     safe_columns = [c.replace("-", "_") for c in columns]

#     conn.execute(
#         f"INSERT INTO load_log ({','.join(safe_columns)}) VALUES ({','.join(['?']*len(values))})",
#         values,
#     )
#     conn.commit()
#     print("📝 ログを記録しました")

def insert_log(row_counts: dict, commit_message: str, csv_path: str = "load_log.csv"):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")

    columns = ["更新日時", "コミットメッセージ"] + SHEET_NAMES
    values  = [now, commit_message] + [row_counts.get(sheet, 0) for sheet in SHEET_NAMES]

    # DB向けにやってた「- → _」をCSVヘッダにも適用するならこちらを使う
    safe_columns = [c.replace("-", "_") for c in columns]

    path = Path(csv_path)
    write_header = not path.exists() or path.stat().st_size == 0

    # Excelで開くことが多いなら utf-8-sig が無難（BOM付きUTF-8）
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        if write_header:
            writer.writerow(safe_columns)

        writer.writerow(values)

    print("📝 ログをCSVに記録しました")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-confirmed", action="store_true",
                        help="確認済み9テーブル+ability_categoryのみ読み込む（non_check_equipmentsをスキップ）")
    args = parser.parse_args()

    target_sheets = CONFIRMED_SHEET_NAMES if args.only_confirmed else SHEET_NAMES

    creds_info, spreadsheet_key = load_credentials_and_key()
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = service_account.Credentials.from_service_account_info(
        creds_info, scopes=scope
    )
    gc = gspread.authorize(credentials)

    conn = sqlite3.connect(DB_FILE)
    row_counts = {}

    spreadsheet = gc.open_by_key(spreadsheet_key)
    for sheet in target_sheets:
        print(f"{sheet} を読み込み中...")
        worksheet = spreadsheet.worksheet(sheet)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        df = cast_dataframe(sheet, df)
        save_to_db(sheet, df, conn)
        row_counts[sheet] = len(df)

    # 確認済み9テーブルに存在する装備を non_check_equipments から除去（non_checkを読み込んだ場合のみ）
    if args.only_confirmed:
        conn.close()
        print(f"🎉 確認済みシートを {DB_FILE} に保存しました（non_check_equipmentsはスキップ）")
        return

    confirmed_tables = [
        "ur武器", "ur防具", "ur装飾",
        "ksr武器", "ksr防具", "ksr装飾",
        "ssr武器", "ssr防具", "ssr装飾",
    ]
    delete_sql = " UNION ALL ".join(
        f"SELECT 装備名, レアリティ FROM {t}" for t in confirmed_tables
    )
    cur = conn.cursor()
    cur.execute(f"""
        SELECT 装備名, レアリティ FROM non_check_equipments
        WHERE (装備名, レアリティ) IN (
            SELECT 装備名, レアリティ FROM ({delete_sql})
        )
    """)
    confirmed_in_non_check = {(r[0], r[1]) for r in cur.fetchall()}

    if confirmed_in_non_check:
        cur.execute(f"""
            DELETE FROM non_check_equipments
            WHERE (装備名, レアリティ) IN (
                SELECT 装備名, レアリティ FROM ({delete_sql})
            )
        """)
        conn.commit()
        print(f"🧹 DB non_check_equipments から確認済み重複 {len(confirmed_in_non_check)} 件を削除しました")

        # SS non_check_equipments からも同じ行を削除
        nc_ws = spreadsheet.worksheet("non_check_equipments")
        all_rows = nc_ws.get_all_values()
        if len(all_rows) > 1:
            header = all_rows[0]
            try:
                name_col = header.index("装備名")
                rarity_col = header.index("レアリティ")
            except ValueError:
                name_col, rarity_col = 0, 2

            # 削除対象の行番号を収集（gspread は1-indexed、ヘッダーが行1→データ先頭は行2）
            # 下から削除することで行番号のずれを防ぐ
            rows_to_delete = [
                i + 2
                for i, row in enumerate(all_rows[1:])
                if (row[name_col], row[rarity_col]) in confirmed_in_non_check
            ]
            for row_num in sorted(rows_to_delete, reverse=True):
                nc_ws.delete_rows(row_num)
            print(f"🧹 SS non_check_equipments から確認済み重複 {len(rows_to_delete)} 件を削除しました")

    # コミットメッセージを取得（無ければ "manual run"）
    commit_message = os.getenv("GITHUB_COMMIT_MESSAGE", "local run")

    # ログテーブル更新
    insert_log(row_counts, commit_message)

    conn.close()
    print(f"🎉 全シートを {DB_FILE} に保存 & ログ更新しました")

if __name__ == "__main__":
    main()
