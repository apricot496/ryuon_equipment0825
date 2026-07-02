from __future__ import annotations

import sqlite3
from pathlib import Path

# ==== 設定（パス事故防止：このファイルと同じ場所の ryuon_equipments.db を参照） ====
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "ryuon_equipments.db"


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def rebuild_equipments_img_scraping(conn: sqlite3.Connection) -> None:
    """
    equipments_img_scraping を (装備名, レアリティ) で1件に圧縮して置き換える。
    URL_Number が小さいものを採用。
    """
    if table_exists(conn, "new_equipments_img_scraping"):
        conn.execute('DROP TABLE "new_equipments_img_scraping"')

    conn.execute(
        """
CREATE TABLE "new_equipments_img_scraping" AS
WITH ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY "装備名", "レアリティ"
      ORDER BY "URL_Number" ASC
    ) AS rn
  FROM "equipments_img_scraping"
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
  "IMG_URL"
FROM ranked
WHERE rn = 1
ORDER BY "URL_Number" ASC;
"""
    )

    conn.execute('DROP TABLE "equipments_img_scraping"')
    conn.execute('ALTER TABLE "new_equipments_img_scraping" RENAME TO "equipments_img_scraping"')


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rebuild_equipments_img_scraping(conn)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
