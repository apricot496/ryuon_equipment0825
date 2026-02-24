import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = "equipment.db"

# DB接続
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""CREATE TABLE new_equipment_img_scraping AS
WITH ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY "装備名", "レアリティ"
      ORDER BY "URL_Number" ASC
    ) AS rn
  FROM equipment_img_scraping
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
""")

# cur.execute("""
# CREATE TABLE new_load_log AS
# WITH grouped_log AS (
#     SELECT 
#         MIN(更新日時) AS 更新日時,
#         'No difference aggregated' AS コミットメッセージ,
#         ur武器,
#         ur防具,
#         ur装飾,
#         ksr武器,
#         ksr防具,
#         ksr装飾,
#         ssr武器,
#         ssr防具,
#         ssr装飾,
#         ability_category
#     FROM load_log
#     GROUP BY 
#         ur武器, ur防具, ur装飾,
#         ksr武器, ksr防具, ksr装飾,
#         ssr武器, ssr防具, ssr装飾,
#         ability_category
# ),
# latest_log AS (
#     SELECT * 
#     FROM load_log
#     ORDER BY 更新日時 DESC
#     LIMIT 1
# )
# SELECT * FROM grouped_log
# UNION ALL
# SELECT * FROM latest_log
# ORDER BY 更新日時 ASC;
# """)

# 元テーブルを置き換えたい場合
cur.execute("DROP TABLE equipment_img_scraping")
cur.execute("ALTER TABLE new_equipment_img_scraping RENAME TO equipment_img_scraping")
# cur.execute("DROP TABLE load_log;")
# cur.execute("ALTER TABLE new_load_log RENAME TO load_log;")

# VACUUMで空き領域を解放
cur.execute("VACUUM;")

conn.commit()
conn.close()

log_path = Path("load_log.csv")
if log_path.exists() and log_path.stat().st_size > 0:
    df = pd.read_csv(log_path, encoding="utf-8-sig")

    if len(df) > 0:
        # 更新日時をdatetime化（フォーマット: YYYY-MM-DD HH:MM:SS を想定）
        df["更新日時_dt"] = pd.to_datetime(df["更新日時"], errors="coerce")

        # グルーピングキー（SQLの GROUP BY と同じ）
        group_keys = [
            "ur武器", "ur防具", "ur装飾",
            "ksr武器", "ksr防具", "ksr装飾",
            "ssr武器", "ssr防具", "ssr装飾",
            "ability_category",
        ]

        # もし列が欠けてたらエラーにせず分かるように落とす
        missing = [c for c in (["更新日時", "コミットメッセージ"] + group_keys) if c not in df.columns]
        if missing:
            raise ValueError(f"load_log.csv に必要な列がありません: {missing}")

        # grouped_log: 同一キーごとに最小更新日時 + コミットメッセージ固定
        grouped = (
            df.groupby(group_keys, dropna=False)
              .agg({"更新日時_dt": "min"})
              .reset_index()
        )
        grouped["更新日時"] = grouped["更新日時_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
        grouped["コミットメッセージ"] = "No difference aggregated"

        # latest_log: 更新日時が最大の行を1件
        latest = (
            df.sort_values("更新日時_dt", ascending=True)
              .tail(1)
              .drop(columns=["更新日時_dt"])
        )

        # grouped_log UNION ALL latest_log → 更新日時昇順
        out_cols = ["更新日時", "コミットメッセージ"] + group_keys
        new_df = pd.concat(
            [grouped[out_cols], latest[out_cols]],
            ignore_index=True
        )

        new_df["更新日時_dt"] = pd.to_datetime(new_df["更新日時"], errors="coerce")
        new_df = new_df.sort_values("更新日時_dt", ascending=True).drop(columns=["更新日時_dt"]).reset_index(drop=True)

        # 置換（安全のため一旦 tmp に書いてから差し替え）
        tmp_path = log_path.with_suffix(".tmp.csv")
        new_df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
        tmp_path.replace(log_path)

        print("📝 load_log.csv を集約して置き換えました")
    else:
        print("load_log.csv が空なので何もしません")
else:
    print("load_log.csv が見つからない/空なので何もしません")
