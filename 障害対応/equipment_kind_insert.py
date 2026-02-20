import sqlite3
from pathlib import Path

DB_PATH = Path("equipment.db")
TARGET_TABLE = "equipment_img_scraping"
TARGET_COL = "装備種別"

# 「武器/防具/装飾」を含むテーブルを参照候補にする
KIND_KEYWORDS = ["武器", "防具", "装飾"]


def col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return any(row[1] == col for row in cur.fetchall())


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def get_tables(conn: sqlite3.Connection):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def infer_kind_from_table_name(table_name: str) -> str | None:
    for k in KIND_KEYWORDS:
        if k in table_name:
            return k
    return None


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH.resolve()}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        if not table_exists(conn, TARGET_TABLE):
            raise FileNotFoundError(f"table not found: {TARGET_TABLE}")

        # 1) カラム追加
        if not col_exists(conn, TARGET_TABLE, TARGET_COL):
            conn.execute(f'ALTER TABLE "{TARGET_TABLE}" ADD COLUMN "{TARGET_COL}" TEXT')
            conn.commit()
            print(f"[OK] added column: {TARGET_TABLE}.{TARGET_COL}")
        else:
            print(f"[SKIP] column exists: {TARGET_TABLE}.{TARGET_COL}")

        # 2) 参照テーブル列挙（DB内にある“武器/防具/装飾”テーブルを自動検出）
        all_tables = get_tables(conn)
        ref_tables = []
        for t in all_tables:
            if t == TARGET_TABLE:
                continue
            kind = infer_kind_from_table_name(t)
            if kind is None:
                continue
            # 参照側に「装備名」カラムが無いテーブルは除外
            if col_exists(conn, t, "装備名"):
                ref_tables.append((t, kind))

        if not ref_tables:
            raise RuntimeError("参照テーブルが見つかりませんでした（テーブル名に 武器/防具/装飾 を含むものが必要）")

        print("[INFO] reference tables:")
        for t, k in ref_tables:
            print(f"  - {t} -> {k}")

        # 3) (装備名 -> 種別) の一時VIEWを作って JOIN UPDATE
        #    同名が複数テーブルにある場合は、最初に見つかったものが入ります（普通は一意想定）
        union_sql_parts = []
        for t, k in ref_tables:
            union_sql_parts.append(f'SELECT 装備名 AS 装備名, "{k}" AS 種別 FROM "{t}"')

        union_sql = "\nUNION ALL\n".join(union_sql_parts)

        conn.execute("DROP VIEW IF EXISTS name_kind_map")
        conn.execute(f"CREATE TEMP VIEW name_kind_map AS {union_sql}")

        # 4) 更新（未設定だけ埋める）
        cur = conn.execute(
            f'''
            UPDATE "{TARGET_TABLE}"
               SET "{TARGET_COL}" = (
                   SELECT m.種別
                     FROM name_kind_map m
                    WHERE m.装備名 = "{TARGET_TABLE}".装備名
                    LIMIT 1
               )
             WHERE ("{TARGET_COL}" IS NULL OR "{TARGET_COL}" = "")
            '''
        )
        conn.commit()
        print(f"[OK] updated rows: {cur.rowcount}")

        # 5) サマリ
        print("\n[SUMMARY] kind counts:")
        cur = conn.execute(f'SELECT "{TARGET_COL}" AS 種別, COUNT(*) AS cnt FROM "{TARGET_TABLE}" GROUP BY "{TARGET_COL}" ORDER BY cnt DESC')
        for r in cur.fetchall():
            print(dict(r))

        cur = conn.execute(
            f'SELECT COUNT(*) AS missing FROM "{TARGET_TABLE}" WHERE "{TARGET_COL}" IS NULL OR "{TARGET_COL}" = ""'
        )
        print("\n[SUMMARY] missing kind rows:", cur.fetchone()["missing"])

    finally:
        conn.close()


if __name__ == "__main__":
    main()
