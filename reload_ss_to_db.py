import os
import gspread
import sqlite3
import pandas as pd
from google.oauth2 import service_account
from dotenv import load_dotenv

def load_secrets():
    load_dotenv()

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
        "universe_domain": os.getenv("GCP_UNIVERSE_DOMAIN")
    }
    spreadsheet_key = os.getenv("SPREADSHEET_KEY_NAME")

    return creds_info, spreadsheet_key


def cast_dataframe(sheet_name: str, df: pd.DataFrame) -> pd.DataFrame:
    """シートごとに型を揃える"""
    if sheet_name != "ability-category":
        # 数値列を強制変換
        if "体力" in df.columns:
            df["体力"] = pd.to_numeric(df["体力"], errors="coerce").astype("Int64")
        if "攻撃力" in df.columns:
            df["攻撃力"] = pd.to_numeric(df["攻撃力"], errors="coerce").astype("Int64")
        if "防御力" in df.columns:
            df["防御力"] = pd.to_numeric(df["防御力"], errors="coerce").astype("Int64")

        for col in ["会心率", "回避率", "命中率"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(1)
    return df


def main():
    creds_info, spreadsheet_key = load_secrets()

    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    credentials = service_account.Credentials.from_service_account_info(
        creds_info, scopes=scope
    )
    gc = gspread.authorize(credentials)

    db_name = "equipment.db"
    conn = sqlite3.connect(db_name)

    sheet_names = [
        "ur武器", "ur防具", "ur装飾",
        "ksr武器", "ksr防具", "ksr装飾",
        "ssr武器", "ssr防具", "ssr装飾",
        "ability-category"
    ]

    for sheet in sheet_names:
        print(f"▶ {sheet} を読み込み中...")
        worksheet = gc.open_by_key(spreadsheet_key).worksheet(sheet)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)

        # 型変換
        df = cast_dataframe(sheet, df)

        table_name = sheet.replace("-", "_")
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"   → {table_name} テーブルに保存 (行数: {len(df)})")

    conn.close()
    print(f"✅ 全シートを {db_name} に保存しました")


if __name__ == "__main__":
    main()
