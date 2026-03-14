from __future__ import annotations

import sqlite3
from pathlib import Path

# ==== 設定（パス事故防止：このファイルと同じ場所の equipment.db を参照） ====
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "equipment.db"


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def rebuild_equipment_img_scraping(conn: sqlite3.Connection) -> None:
    """
    equipment_img_scraping を (装備名, レアリティ) で1件に圧縮して置き換える。
    URL_Number が小さいものを採用。
    """
    if table_exists(conn, "new_equipment_img_scraping"):
        conn.execute('DROP TABLE "new_equipment_img_scraping"')

    conn.execute(
        """
CREATE TABLE "new_equipment_img_scraping" AS
WITH ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY "装備名", "レアリティ"
      ORDER BY "URL_Number" ASC
    ) AS rn
  FROM "equipment_img_scraping"
  WHERE "装備名" IS NOT NULL
)
SELECT
  "装備名",
  "レアリティ",
  "画像名",
  "体力",
  "攻撃力",
  "防御力",
  "会心率",
  "回避率",
  "命中率",
  "アビリティ",
  "新規フラグ",
  "URL_Number",
  "IMG_URL",
  "IMG_Path",
  "BASE64"
FROM ranked
WHERE rn = 1
ORDER BY "URL_Number" ASC;
"""
    )

    conn.execute('DROP TABLE "equipment_img_scraping"')
    conn.execute('ALTER TABLE "new_equipment_img_scraping" RENAME TO "equipment_img_scraping"')


def vacuum(conn: sqlite3.Connection) -> None:
    """
    VACUUM はトランザクション外で実行する必要があることが多いので、
    commit後に実行する。
    """
    conn.execute("VACUUM")


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rebuild_equipment_img_scraping(conn)
        conn.commit()
        vacuum(conn)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
