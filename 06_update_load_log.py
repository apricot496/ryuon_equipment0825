#!/usr/bin/env python3

import csv
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path("ryuon_equipments.db")
CSV_PATH = Path("load_log.csv")
JST = timezone(timedelta(hours=9))

FIXED_TABLES = ["mst_ability_category", "unconfirmed_equipments"]


def fetch_counts() -> dict[str, int]:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} が見つかりません")

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        # confirmed_* テーブルを動的に検出 + 固定テーブルを追加
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'confirmed_%' ORDER BY name"
        )
        table_names = [row[0] for row in cur.fetchall()] + FIXED_TABLES

        counts = {}
        for table_name in table_names:
            cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            row = cur.fetchone()
            counts[table_name] = int(row[0]) if row else 0
        return counts
    finally:
        conn.close()


def load_rows() -> list[dict[str, str]]:
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return []
    with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def has_difference(rows: list[dict[str, str]], counts: dict[str, int]) -> bool:
    if not rows:
        return True
    last_row = rows[-1]
    for table_name, new_value in counts.items():
        try:
            old_value = int(last_row.get(table_name, 0))
        except Exception:
            return True
        if old_value != new_value:
            return True
    return False


def build_change_message(last_row: dict[str, str] | None, counts: dict[str, int]) -> str:
    if last_row is None:
        return "Initial record"
    changes = []
    for table_name, new_value in counts.items():
        try:
            old_value = int(last_row.get(table_name, 0))
        except Exception:
            old_value = 0
        if old_value != new_value:
            changes.append(f"{table_name}:{old_value}→{new_value}")
    return "\n".join(changes) if changes else "No difference"


def build_row(last_row: dict[str, str] | None, counts: dict[str, int]) -> dict:
    return {
        "更新日時": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
        "コミットメッセージ": build_change_message(last_row, counts),
        **counts,
    }


def write_rows(rows: list[dict], fieldnames: list[str]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def update_csv_if_needed(counts: dict[str, int]) -> bool:
    fieldnames = ["更新日時", "コミットメッセージ"] + list(counts.keys())
    rows = load_rows()
    last_row = rows[-1] if rows else None

    if not has_difference(rows, counts):
        print("差分なし: load_log.csv は更新しませんでした")
        return False

    rows.append(build_row(last_row, counts))
    write_rows(rows, fieldnames)
    print("差分あり: load_log.csv を更新しました")
    return True


def main() -> None:
    counts = fetch_counts()
    update_csv_if_needed(counts)


if __name__ == "__main__":
    main()
