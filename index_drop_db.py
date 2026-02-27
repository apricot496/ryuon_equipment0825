from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd

# ==== 設定（パス事故防止：このファイルと同じ場所の equipment.db を参照） ====
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "equipment.db"
LOG_PATH = BASE_DIR / "load_log.csv"


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def count_rows(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def rebuild_equipment_img_scraping(conn: sqlite3.Connection) -> None:
    """
    equipment_img_scraping を (装備名, レアリティ) で1件に圧縮して置き換える。
    URL_Number が小さいものを採用。
    """
    # 既存 new_ が残ってたら消す
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

    # 置き換え
    conn.execute('DROP TABLE "equipment_img_scraping"')
    conn.execute('ALTER TABLE "new_equipment_img_scraping" RENAME TO "equipment_img_scraping"')


def vacuum(conn: sqlite3.Connection) -> None:
    """
    VACUUM はトランザクション外で実行する必要があることが多いので、
    commit後に実行する。
    """
    conn.execute("VACUUM")


def normalize_load_log_csv(log_path: Path, db_path: Path) -> None:
    """
    load_log.csv を集約して置き換える。
    - group_keys に non_check_equipments を含める
    - CSVに non_check_equipments 列が無ければ追加（※あなたは既に追加済みだが保険）
    - さらに「最新行」の non_check_equipments が 0/空 なら DBから行数を取って補完
    """
    if not log_path.exists() or log_path.stat().st_size == 0:
        print("load_log.csv が見つからない/空なので何もしません")
        return

    df = pd.read_csv(log_path, encoding="utf-8-sig")
    if len(df) == 0:
        print("load_log.csv が空なので何もしません")
        return

    # 必須列チェック
    must = ["更新日時", "コミットメッセージ"]
    missing_must = [c for c in must if c not in df.columns]
    if missing_must:
        raise ValueError(f"load_log.csv に必須列がありません: {missing_must}")

    # non_check_equipments 列が無ければ作る
    if "non_check_equipments" not in df.columns:
        df["non_check_equipments"] = 0

    # 更新日時をdatetime化
    df["更新日時_dt"] = pd.to_datetime(df["更新日時"], errors="coerce")

    # グルーピングキー
    group_keys = [
        "ur武器", "ur防具", "ur装飾",
        "ksr武器", "ksr防具", "ksr装飾",
        "ssr武器", "ssr防具", "ssr装飾",
        "ability_category",
        "non_check_equipments",
    ]

    # 欠けてる列はここで分かるように落とす
    missing = [c for c in group_keys if c not in df.columns]
    if missing:
        raise ValueError(f"load_log.csv に必要な列がありません: {missing}")

    # ★ 追加：最新行の non_check_equipments が 0/空なら DBの行数で補完しておく
    # （「更新があった際に non_check の行数が出力されない」問題の救済）
    try:
        # 空文字などを数値化（できないものはNaN）
        df["non_check_equipments"] = pd.to_numeric(df["non_check_equipments"], errors="coerce")
        last_idx = df["更新日時_dt"].sort_values().index[-1]
        last_val = df.loc[last_idx, "non_check_equipments"]
        if pd.isna(last_val) or int(last_val) == 0:
            conn = sqlite3.connect(str(db_path))
            if table_exists(conn, "non_check_equipments"):
                df.loc[last_idx, "non_check_equipments"] = count_rows(conn, "non_check_equipments")
            conn.close()
    except Exception:
        # 補完で落ちるのは本末転倒なので無視（集約自体は続行）
        pass

    # grouped_log: 同一キーごとに最小更新日時 + メッセージ固定
    grouped = (
        df.groupby(group_keys, dropna=False)
          .agg({"更新日時_dt": "min"})
          .reset_index()
    )
    grouped["更新日時"] = grouped["更新日時_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    grouped["コミットメッセージ"] = "No difference aggregated"

    # latest_log: 更新日時が最大の行を1件（元のメッセージを残す）
    latest = (
        df.sort_values("更新日時_dt", ascending=True)
          .tail(1)
          .drop(columns=["更新日時_dt"])
    )

    out_cols = ["更新日時", "コミットメッセージ"] + group_keys
    new_df = pd.concat([grouped[out_cols], latest[out_cols]], ignore_index=True)

    new_df["更新日時_dt"] = pd.to_datetime(new_df["更新日時"], errors="coerce")
    new_df = (
        new_df.sort_values("更新日時_dt", ascending=True)
              .drop(columns=["更新日時_dt"])
              .reset_index(drop=True)
    )

    # 置換（安全のため tmp に書いて差し替え）
    tmp_path = log_path.with_suffix(".tmp.csv")
    new_df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    tmp_path.replace(log_path)

    print("📝 load_log.csv を集約して置き換えました")


def main() -> None:
    # DB加工（equipment_img_scraping の重複排除）
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rebuild_equipment_img_scraping(conn)
        conn.commit()
        vacuum(conn)  # commit後に実行（安全）
        conn.commit()
    finally:
        conn.close()

    # ログCSVの集約・補完
    normalize_load_log_csv(LOG_PATH, DB_PATH)


if __name__ == "__main__":
    main()
