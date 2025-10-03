import os
import json
import sqlite3
import pandas as pd
import gspread
from google.oauth2 import service_account
from dotenv import load_dotenv

DB_FILE = "equipment.db"
SHEET_NAMES = [
    "ur武器", "ur防具", "ur装飾",
    "ksr武器", "ksr防具", "ksr装飾",
    "ssr武器", "ssr防具", "ssr装飾",
    "ability-category"
]

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
    if sheet_name != "ability-category":
        # int列
        for col in ["体力", "攻撃力", "防御力"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                # 小数が混じっていないかチェック
                if (df[col].dropna() % 1 != 0).any():
                    raise ValueError(f"{sheet_name} の {col} 列に小数が含まれています。修正してください。")
                df[col] = df[col].astype("Int64")

        # float列
        for col in ["会心率", "回避率", "命中率"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(1)

    return df

def save_to_db(sheet_name: str, df: pd.DataFrame, conn: sqlite3.Connection):
    df.to_sql(sheet_name, conn, if_exists="replace", index=False)
    print(f"✅ {sheet_name} を保存しました")

def main():
    creds_info, spreadsheet_key = load_credentials_and_key()
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = service_account.Credentials.from_service_account_info(
        creds_info, scopes=scope
    )
    gc = gspread.authorize(credentials)

    conn = sqlite3.connect(DB_FILE)

    for sheet in SHEET_NAMES:
        print(f"{sheet} を読み込み中...")
        worksheet = gc.open_by_key(spreadsheet_key).worksheet(sheet)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        df = cast_dataframe(sheet, df)
        save_to_db(sheet, df, conn)

    conn.close()
    print(f"🎉 全シートを {DB_FILE} に保存しました")

if __name__ == "__main__":
    main()
