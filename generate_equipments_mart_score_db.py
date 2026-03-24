"""
装備スコアDB生成スクリプト
- equipments_mart_score.db を生成
- {yyyymmdd}_equipments_mart_score テーブル作成
- {yyyymmdd}_max_status_score テーブル作成
- 前回と同一内容なら当日テーブル作成を省略
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ability_evaluator import evaluate_ability
from export_mart_with_scores import (
    STATUS_COLUMNS,
    analyze_build_type,
    calculate_build_type_combination_rankings,
    calculate_overall_status_score,
    calculate_status_rankings,
)

SOURCE_DB = "equipment.db"
OUTPUT_DB = "equipments_mart_score.db"

STATUS_LIST = ["体力", "攻撃力", "防御力", "会心率", "命中率", "回避率"]
MAX_STATUS_INDEX = ["体力", "攻撃力", "防御力", "会心率", "命中率", "回避率"]


def _to_numeric_safe(df: pd.DataFrame, cols: List[str], as_int: bool = False) -> None:
    for col in cols:
        if col not in df.columns:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if as_int:
            df[col] = df[col].round().astype("Int64")


def build_mart_score_dataframe(source_conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM mart_equipments_master", source_conn)

    # 装備番号は equipment.db の mart_equipments_master 由来を明示
    # 装備番号は文字列ID（例: 0_0_0_001）なので文字列として保持
    # 欠損時は同一(装備名, レアリティ)の代表値で補完
    if "装備番号" in df.columns:
        df["装備番号"] = df["装備番号"].astype(str)
        df.loc[df["装備番号"].isin(["", "nan", "None"]), "装備番号"] = pd.NA
        fallback = (
            df[["装備名", "レアリティ", "装備番号"]]
            .dropna(subset=["装備番号"])
            .drop_duplicates(subset=["装備名", "レアリティ"], keep="first")
            .rename(columns={"装備番号": "_fallback_装備番号"})
        )
        if not fallback.empty:
            df = df.merge(fallback, on=["装備名", "レアリティ"], how="left")
            df["装備番号"] = df["装備番号"].fillna(df["_fallback_装備番号"])
            df = df.drop(columns=["_fallback_装備番号"])

    status_scores = []
    status_score_types = []
    ability_scores = []
    build_types = []

    detail_cols: Dict[str, List] = {
        "ステータス数": [],
        "ランクイン数_5位以内": [],
        "ランクイン数_10位以内": [],
        "最高ステータススコア": [],
        "平均ステータススコア": [],
        "発動条件": [],
        "アビリティ_重要度": [],
        "アビリティ_発動条件": [],
        "アビリティ_効果量スコア": [],
        "アビリティ_抽出効果値": [],
        "アビリティ_代表カテゴリ": [],
        "アビリティ_min効果値": [],
        "アビリティ_max効果値": [],
    }

    for stat in STATUS_LIST:
        detail_cols[f"{stat}_rank"] = []
        detail_cols[f"{stat}_total"] = []
        detail_cols[f"{stat}_score"] = []
        detail_cols[f"{stat}_value"] = []
        detail_cols[f"{stat}_min"] = []
        detail_cols[f"{stat}_max"] = []
        detail_cols[f"{stat}_diff"] = []

    for idx, row in df.iterrows():
        equipment = row.to_dict()

        rankings = calculate_status_rankings(source_conn, equipment)
        build_type, build_type_statuses = analyze_build_type(equipment, rankings)
        build_type_rankings = calculate_build_type_combination_rankings(
            source_conn,
            equipment,
            build_type_statuses,
        )

        if build_type_rankings:
            best_build = max(build_type_rankings.values(), key=lambda x: x["score"])
            build_type = f'{best_build["build_type"]}({best_build["combo_name"]})'

        status_score, score_type = calculate_overall_status_score(rankings, build_type_rankings)

        stat_scores = []
        rank5_count = 0
        rank10_count = 0

        for stat in STATUS_LIST:
            if stat in rankings:
                rank_data = rankings[stat]
                detail_cols[f"{stat}_rank"].append(rank_data["rank"])
                detail_cols[f"{stat}_total"].append(rank_data["total"])
                detail_cols[f"{stat}_score"].append(rank_data["score"])
                detail_cols[f"{stat}_value"].append(rank_data["value"])
                detail_cols[f"{stat}_min"].append(rank_data["min"])
                detail_cols[f"{stat}_max"].append(rank_data["max"])
                detail_cols[f"{stat}_diff"].append(rank_data["diff"])

                stat_scores.append(rank_data["score"])
                if rank_data["rank"] <= 5:
                    rank5_count += 1
                if rank_data["rank"] <= 10:
                    rank10_count += 1
            else:
                detail_cols[f"{stat}_rank"].append(None)
                detail_cols[f"{stat}_total"].append(None)
                detail_cols[f"{stat}_score"].append(None)
                detail_cols[f"{stat}_value"].append(None)
                detail_cols[f"{stat}_min"].append(None)
                detail_cols[f"{stat}_max"].append(None)
                detail_cols[f"{stat}_diff"].append(None)

        detail_cols["ステータス数"].append(len(stat_scores))
        detail_cols["ランクイン数_5位以内"].append(rank5_count)
        detail_cols["ランクイン数_10位以内"].append(rank10_count)
        detail_cols["最高ステータススコア"].append(max(stat_scores) if stat_scores else 0)
        detail_cols["平均ステータススコア"].append(sum(stat_scores) / len(stat_scores) if stat_scores else 0)

        ability_text = equipment.get("アビリティ", "")
        ability_category = equipment.get("アビリティカテゴリ", "")
        equipment_type = equipment.get("装備種類", "")

        if ability_text and ability_category and equipment_type and ability_category != "なし":
            ability_result = evaluate_ability(
                ability_text,
                ability_category,
                equipment_type,
                equipment_name=equipment.get("装備名"),
                rarity=equipment.get("レアリティ"),
            )
            ability_score = ability_result.get("score", 0.0)
            detail_cols["発動条件"].append(ability_result.get("condition_text", ""))
            detail_cols["アビリティ_重要度"].append(ability_result.get("importance", 0))
            detail_cols["アビリティ_発動条件"].append(ability_result.get("condition_rate", 0))
            detail_cols["アビリティ_効果量スコア"].append(ability_result.get("effect_score", 0))
            detail_cols["アビリティ_抽出効果値"].append(ability_result.get("effect_value", None))
            detail_cols["アビリティ_代表カテゴリ"].append(ability_result.get("representative_category", ""))
            detail_cols["アビリティ_min効果値"].append(ability_result.get("min_effect_value", None))
            detail_cols["アビリティ_max効果値"].append(ability_result.get("max_effect_value", None))
        else:
            ability_score = 0.0
            detail_cols["発動条件"].append("")
            detail_cols["アビリティ_重要度"].append(0)
            detail_cols["アビリティ_発動条件"].append(0)
            detail_cols["アビリティ_効果量スコア"].append(0)
            detail_cols["アビリティ_抽出効果値"].append(None)
            detail_cols["アビリティ_代表カテゴリ"].append("")
            detail_cols["アビリティ_min効果値"].append(None)
            detail_cols["アビリティ_max効果値"].append(None)

        status_scores.append(status_score)
        status_score_types.append(score_type)
        ability_scores.append(ability_score)
        build_types.append(build_type)

        if (idx + 1) % 200 == 0:
            print(f"処理中... {idx + 1}/{len(df)}")

    df["ステータススコア"] = status_scores
    df["ステータス評価種別"] = status_score_types
    df["アビリティスコア"] = ability_scores
    df["ビルドタイプ"] = build_types

    for col_name, values in detail_cols.items():
        df[col_name] = values

    int_like_cols = [
        "ステータス数",
        "ランクイン数_5位以内",
        "ランクイン数_10位以内",
    ] + [
        f"{stat}_rank" for stat in STATUS_LIST
    ] + [
        f"{stat}_total" for stat in STATUS_LIST
    ]

    float_cols = [
        "体力", "攻撃力", "防御力", "会心率", "命中率", "回避率",
        "ステータススコア", "アビリティスコア",
        "最高ステータススコア", "平均ステータススコア",
        "アビリティ_重要度", "アビリティ_発動条件", "アビリティ_効果量スコア",
        "アビリティ_抽出効果値", "アビリティ_min効果値", "アビリティ_max効果値",
    ] + [
        f"{stat}_score" for stat in STATUS_LIST
    ] + [
        f"{stat}_value" for stat in STATUS_LIST
    ] + [
        f"{stat}_min" for stat in STATUS_LIST
    ] + [
        f"{stat}_max" for stat in STATUS_LIST
    ] + [
        f"{stat}_diff" for stat in STATUS_LIST
    ]

    _to_numeric_safe(df, int_like_cols, as_int=True)
    _to_numeric_safe(df, float_cols, as_int=False)

    # カラムを用途ごとに整理（基本情報 → ステータス用 → アビリティ用 → その他）
    base_info_cols = [
        "装備番号",
        "装備名",
        "レアリティ",
        "装備種類",
        "属性",
        "特性",
    ]

    status_related_cols = [
        "体力",
        "攻撃力",
        "防御力",
        "会心率",
        "命中率",
        "回避率",
        "ステータススコア",
        "ステータス評価種別",
        "ビルドタイプ",
        "ステータス数",
        "ランクイン数_5位以内",
        "ランクイン数_10位以内",
        "最高ステータススコア",
        "平均ステータススコア",
    ]

    for stat in STATUS_LIST:
        status_related_cols.extend(
            [
                f"{stat}_rank",
                f"{stat}_total",
                f"{stat}_score",
                f"{stat}_value",
                f"{stat}_min",
                f"{stat}_max",
                f"{stat}_diff",
            ]
        )

    ability_related_cols = [
        "アビリティ",
        "アビリティカテゴリ",
        "発動条件",
        "アビリティスコア",
        "アビリティ_重要度",
        "アビリティ_発動条件",
        "アビリティ_効果量スコア",
        "アビリティ_抽出効果値",
        "アビリティ_代表カテゴリ",
        "アビリティ_min効果値",
        "アビリティ_max効果値",
    ]

    ordered_cols: List[str] = []
    for col in base_info_cols + status_related_cols + ability_related_cols:
        if col in df.columns and col not in ordered_cols:
            ordered_cols.append(col)

    remaining_cols = [col for col in df.columns if col not in ordered_cols]
    df = df[ordered_cols + remaining_cols]

    return df


def _build_json_payload(row: pd.Series, index_stat: str) -> str:
    payload = {"装備名": row.get("装備名")}

    equipment_no = row.get("装備番号")
    if pd.notna(equipment_no):
        payload["装備番号"] = str(equipment_no)

    value = row.get(index_stat)
    if pd.notna(value) and float(value) != 0:
        payload[index_stat] = float(value)

    atk = row.get("攻撃力")
    if pd.notna(atk) and float(atk) != 0:
        payload["攻撃力"] = float(atk)

    crit = row.get("会心率")
    if pd.notna(crit) and float(crit) != 0:
        payload["会心率"] = float(crit)

    ability = row.get("アビリティ")
    if pd.notna(ability) and str(ability).strip() not in ("", "0"):
        payload["アビリティ"] = str(ability)

    return json.dumps(payload, ensure_ascii=False)


def build_max_status_score_dataframe(df_scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    equipment_types = ["武器", "防具", "装飾"]

    for index_stat in MAX_STATUS_INDEX:
        row_data = {"index": index_stat, "武器": None, "防具": None, "装飾": None, "計": 0.0}
        total = 0.0

        for eq_type in equipment_types:
            sub = df_scores[df_scores["装備種類"] == eq_type].copy()
            sub[index_stat] = pd.to_numeric(sub[index_stat], errors="coerce")
            sub = sub[sub[index_stat] > 0]

            if sub.empty:
                row_data[eq_type] = json.dumps({}, ensure_ascii=False)
                continue

            sub = sub.sort_values(by=[index_stat, "アビリティスコア"], ascending=[False, False])
            top_row = sub.iloc[0]

            row_data[eq_type] = _build_json_payload(top_row, index_stat)
            total += float(top_row[index_stat])

        row_data["計"] = float(total)
        rows.append(row_data)

    return pd.DataFrame(rows, columns=["index", "武器", "防具", "装飾", "計"])


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cur.fetchone() is not None


def _find_latest_table(conn: sqlite3.Connection, suffix: str, current_date: str) -> Optional[str]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    pattern = re.compile(rf"^(\d{{8}})_{re.escape(suffix)}$")

    candidates: List[Tuple[str, str]] = []
    for (name,) in cur.fetchall():
        m = pattern.match(name)
        if not m:
            continue
        date_part = m.group(1)
        if date_part < current_date:
            candidates.append((date_part, name))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _normalize_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    normalized = normalized.sort_values(by=list(normalized.columns), na_position="first").reset_index(drop=True)

    for col in normalized.columns:
        if pd.api.types.is_numeric_dtype(normalized[col]):
            normalized[col] = normalized[col].round(8)
        else:
            normalized[col] = normalized[col].fillna("").astype(str)

    return normalized


def _is_same_as_previous(conn: sqlite3.Connection, current_df: pd.DataFrame, suffix: str, current_date: str) -> bool:
    prev_table = _find_latest_table(conn, suffix, current_date)
    if not prev_table:
        return False

    prev_df = pd.read_sql(f'SELECT * FROM "{prev_table}"', conn)

    curr_norm = _normalize_for_compare(current_df)
    prev_norm = _normalize_for_compare(prev_df)

    if list(curr_norm.columns) != list(prev_norm.columns):
        return False

    return curr_norm.equals(prev_norm)


def _write_table(conn: sqlite3.Connection, table_name: str, df: pd.DataFrame) -> None:
    conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    df.to_sql(table_name, conn, if_exists="replace", index=False)


def main() -> None:
    current_date = datetime.now().strftime("%Y%m%d")
    score_table = f"{current_date}_equipments_mart_score"
    max_status_table = f"{current_date}_max_status_score"

    source_conn = sqlite3.connect(SOURCE_DB)
    score_df = build_mart_score_dataframe(source_conn)
    source_conn.close()

    max_status_df = build_max_status_score_dataframe(score_df)

    output_db_path = Path(OUTPUT_DB)
    output_conn = sqlite3.connect(output_db_path)

    score_same = _is_same_as_previous(output_conn, score_df, "equipments_mart_score", current_date)
    max_same = _is_same_as_previous(output_conn, max_status_df, "max_status_score", current_date)

    created_tables = []
    skipped_tables = []

    if score_same:
        skipped_tables.append(score_table)
    else:
        _write_table(output_conn, score_table, score_df)
        created_tables.append(score_table)

    if max_same:
        skipped_tables.append(max_status_table)
    else:
        _write_table(output_conn, max_status_table, max_status_df)
        created_tables.append(max_status_table)

    output_conn.close()

    print("=" * 60)
    print("equipments_mart_score.db 生成結果")
    print("=" * 60)
    if created_tables:
        for t in created_tables:
            print(f"✓ 作成/更新: {t}")
    if skipped_tables:
        for t in skipped_tables:
            print(f"⏭ 省略（前回同一）: {t}")


if __name__ == "__main__":
    main()
