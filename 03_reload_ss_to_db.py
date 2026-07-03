import os
import sqlite3
import pandas as pd
import gspread
from google.oauth2 import service_account
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv

DB_FILE = "ryuon_equipments.db"
UNCONFIRMED_SHEET = "unconfirmed_equipments"
JST = timezone(timedelta(hours=9))

# SSシート名とDBテーブル名が異なる場合のマッピング
SHEET_TO_TABLE: dict[str, str] = {
    "ability_category": "mst_ability_category",
}


def load_credentials_and_key():
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
    if sheet_name == "ability_category":
        return df
    for col in ["体力", "攻撃力", "防御力"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if (df[col].dropna() % 1 != 0).any():
                raise ValueError(f"{sheet_name} の {col} 列に小数が含まれています。修正してください。")
            df[col] = df[col].astype("Int64")
    for col in ["会心率", "回避率", "命中率"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(1)
    return df


def save_to_db(sheet_name: str, df: pd.DataFrame, conn: sqlite3.Connection):
    if "装備名" in df.columns:
        df = df[df["装備名"] != "装備名"]
    table_name = SHEET_TO_TABLE.get(sheet_name, sheet_name)
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    print(f"✅ {sheet_name} を保存しました ({len(df)}件)")


def insert_log(row_counts: dict, sheet_names: list, commit_message: str, csv_path: str = "load_log.csv"):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    columns = ["更新日時", "コミットメッセージ"] + list(sheet_names)
    values = [now, commit_message] + [row_counts.get(s, 0) for s in sheet_names]
    safe_columns = [c.replace("-", "_") for c in columns]

    path = Path(csv_path)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(safe_columns)
        writer.writerow(values)
    print("📝 ログをCSVに記録しました")


def _get_confirmed_table_names_from_db(conn: sqlite3.Connection) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'confirmed_%' ORDER BY name"
    )
    return [row[0] for row in cur.fetchall()]


def main():
    creds_info, spreadsheet_key = load_credentials_and_key()
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(credentials)

    conn = sqlite3.connect(DB_FILE)

    # confirmed_* テーブルを DB から検出（初回は空のためフォールバックあり）
    confirmed_from_db = _get_confirmed_table_names_from_db(conn)

    spreadsheet = gc.open_by_key(spreadsheet_key)

    if confirmed_from_db:
        confirmed_sheet_names = confirmed_from_db
    else:
        # 初回実行など DB に confirmed_* がない場合は SS ワークシート一覧から検出
        all_ws = spreadsheet.worksheets()
        confirmed_sheet_names = sorted([ws.title for ws in all_ws if ws.title.startswith("confirmed_")])
        print("⚠️  DB に confirmed_* テーブルがないため SS から検出しました")

    target_sheets = confirmed_sheet_names + ["ability_category", UNCONFIRMED_SHEET]
    print(f"読み込み対象: {target_sheets}")

    row_counts = {}
    for sheet in target_sheets:
        print(f"{sheet} を読み込み中...")
        try:
            worksheet = spreadsheet.worksheet(sheet)
        except gspread.WorksheetNotFound:
            print(f"⚠️  {sheet} シートが見つかりません。スキップします")
            row_counts[sheet] = 0
            continue
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        df = cast_dataframe(sheet, df)
        save_to_db(sheet, df, conn)
        row_counts[sheet] = len(df)

    # confirmed_* テーブルに存在する装備を unconfirmed_equipments から除去
    confirmed_db_tables = _get_confirmed_table_names_from_db(conn)
    if confirmed_db_tables:
        delete_sql = " UNION ALL ".join(
            f'SELECT 装備名, レアリティ FROM "{t}"' for t in confirmed_db_tables
        )
        cur = conn.cursor()
        cur.execute(f"""
            SELECT 装備名, レアリティ FROM unconfirmed_equipments
            WHERE (装備名, レアリティ) IN (
                SELECT 装備名, レアリティ FROM ({delete_sql})
            )
        """)
        confirmed_in_unconfirmed = {(r[0], r[1]) for r in cur.fetchall()}

        if confirmed_in_unconfirmed:
            cur.execute(f"""
                DELETE FROM unconfirmed_equipments
                WHERE (装備名, レアリティ) IN (
                    SELECT 装備名, レアリティ FROM ({delete_sql})
                )
            """)
            conn.commit()
            print(f"🧹 DB unconfirmed_equipments から確認済み重複 {len(confirmed_in_unconfirmed)} 件を削除しました")

            # SS unconfirmed_equipments からも削除（clear + rewrite で2リクエスト）
            nc_ws = spreadsheet.worksheet(UNCONFIRMED_SHEET)
            all_rows = nc_ws.get_all_values()
            if len(all_rows) > 1:
                header = all_rows[0]
                try:
                    name_col = header.index("装備名")
                    rarity_col = header.index("レアリティ")
                except ValueError:
                    name_col, rarity_col = 0, 2

                kept_rows = [header] + [
                    row for row in all_rows[1:]
                    if (row[name_col], row[rarity_col]) not in confirmed_in_unconfirmed
                ]
                removed_count = len(all_rows) - len(kept_rows)
                if removed_count > 0:
                    nc_ws.clear()
                    nc_ws.update(kept_rows, "A1")
                    print(f"🧹 SS {UNCONFIRMED_SHEET} から確認済み重複 {removed_count} 件を削除しました")

    commit_message = os.getenv("GITHUB_COMMIT_MESSAGE", "local run")
    insert_log(row_counts, target_sheets, commit_message)

    conn.close()
    print(f"🎉 全シートを {DB_FILE} に保存 & ログ更新しました")


if __name__ == "__main__":
    main()
