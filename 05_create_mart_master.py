import sqlite3
import pandas as pd

DB_FILE = "ryuon_equipments.db"
EQUIP_TYPES = ["武器", "防具", "装飾"]


def create_mart_equipments_master():
    """
    confirmed_* テーブル（動的検出）と unconfirmed_equipments を統合して
    mart_equipments_master テーブルを作成する
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # confirmed_* テーブルを DB から動的に検出
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'confirmed_%' ORDER BY name"
    )
    confirmed_tables = [row[0] for row in cur.fetchall()]

    if not confirmed_tables:
        print("⚠️  confirmed_* テーブルが見つかりません。処理を中断します")
        conn.close()
        return

    all_df_list = []

    for table_name in confirmed_tables:
        print(f"Reading {table_name}...")
        df = pd.read_sql(f'SELECT * FROM "{table_name}"', conn)

        # 装備種類列がない or 全空の場合はテーブル名から推測
        if "装備種類" not in df.columns or df["装備種類"].replace("", pd.NA).isna().all():
            equip_type = next((t for t in EQUIP_TYPES if table_name.endswith(t)), None)
            if equip_type:
                df["装備種類"] = equip_type

        all_df_list.append(df)

    # unconfirmed_equipments を読み込み
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='unconfirmed_equipments'"
    )
    if cur.fetchone():
        print("Reading unconfirmed_equipments...")
        df_unconfirmed = pd.read_sql("SELECT * FROM unconfirmed_equipments", conn)
        all_df_list.append(df_unconfirmed)
    else:
        print("⚠️  unconfirmed_equipments テーブルが見つかりません")

    print("Concatenating all dataframes...")
    master_df = pd.concat(all_df_list, ignore_index=True)

    print("Normalizing data types...")
    for col in ["体力", "攻撃力", "防御力"]:
        if col in master_df.columns:
            master_df[col] = pd.to_numeric(master_df[col], errors="coerce").astype("Int64")

    for col in ["会心率", "回避率", "命中率"]:
        if col in master_df.columns:
            master_df[col] = pd.to_numeric(master_df[col], errors="coerce")

    for col in ["装備名", "装備番号", "レアリティ", "アビリティ", "アビリティカテゴリ", "装備種類"]:
        if col in master_df.columns:
            master_df[col] = master_df[col].astype(str).replace("nan", None)

    print("Creating mart_equipments_master table...")
    cur.execute("DROP TABLE IF EXISTS mart_equipments_master")
    master_df.to_sql("mart_equipments_master", conn, if_exists="replace", index=False)

    count = cur.execute("SELECT COUNT(*) FROM mart_equipments_master").fetchone()[0]
    print(f"✓ mart_equipments_master に {count} 件のレコードを作成しました")

    for row in cur.execute("SELECT 装備種類, COUNT(*) FROM mart_equipments_master GROUP BY 装備種類"):
        print(f"  - {row[0]}: {row[1]}件")

    conn.close()
    print("\nmart_equipments_master 作成完了!")


if __name__ == "__main__":
    create_mart_equipments_master()
