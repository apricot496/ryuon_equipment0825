"""
mart_equipments_masterをスコアと共にExcelにエクスポート
評価指標の見直し用
"""
import sqlite3
import pandas as pd
from typing import Dict, Optional
from ability_evaluator import evaluate_ability
from itertools import combinations

DB_FILE = "equipment.db"

# 全装備種類で全ステータスを評価対象とする
STATUS_COLUMNS = {
    "武器": ["体力", "攻撃力", "防御力", "会心率", "回避率", "命中率"],
    "防具": ["体力", "攻撃力", "防御力", "会心率", "回避率", "命中率"],
    "装飾": ["体力", "攻撃力", "防御力", "会心率", "回避率", "命中率"]
}


def calculate_status_rankings(conn: sqlite3.Connection, equipment: Dict) -> Dict:
    """
    同装備種類内でのステータスランキングを計算
    
    - 体力、攻撃力、防御力: 同装備種類 AND 同レアリティで比較
    - 会心率、回避率、命中率: 同装備種類のみで比較
    """
    equipment_type = equipment["装備種類"]
    rarity = equipment.get("レアリティ")
    
    if not equipment_type or equipment_type not in STATUS_COLUMNS:
        return {}
    
    status_cols = STATUS_COLUMNS[equipment_type]
    rankings = {}
    
    # レアリティで区分するステータス
    rarity_based_stats = ["体力", "攻撃力", "防御力"]
    
    for status in status_cols:
        # 現在の装備のステータス値を取得
        current_value = equipment.get(status)
        
        # NaN、None、0をスキップ
        if pd.isna(current_value) or current_value is None or current_value == 0:
            continue
        
        try:
            current_value = float(current_value)
        except (ValueError, TypeError):
            continue
        
        # ステータスに応じてフィルタ条件を変更
        if status in rarity_based_stats:
            # 体力・攻撃力・防御力: 同装備種類 AND 同レアリティ
            df = pd.read_sql(f"""
                SELECT {status}, 装備名, レアリティ
                FROM mart_equipments_master
                WHERE 装備種類 = ? AND レアリティ = ? AND {status} IS NOT NULL AND {status} > 0
                ORDER BY {status} DESC
            """, conn, params=(equipment_type, rarity))
        else:
            # 会心率・回避率・命中率: 同装備種類のみ
            df = pd.read_sql(f"""
                SELECT {status}, 装備名, レアリティ
                FROM mart_equipments_master
                WHERE 装備種類 = ? AND {status} IS NOT NULL AND {status} > 0
                ORDER BY {status} DESC
            """, conn, params=(equipment_type,))
        
        if df.empty:
            continue
        
        # ランキング計算
        total_count = len(df)
        rank = (df[status] > current_value).sum() + 1
        max_value = df[status].max()
        min_value = df[status].min()
        diff = max_value - current_value
        
        # スコア計算（最低値〜最高値の範囲で0〜100点）
        if max_value == min_value:
            # 最高値=最低値（1つしかデータがない、または全て同じ値）
            score = 100.0
        else:
            score = 100.0 * (current_value - min_value) / (max_value - min_value)
        
        rankings[status] = {
            "rank": rank,
            "total": total_count,
            "diff": diff,
            "value": current_value,
            "max": max_value,
            "min": min_value,
            "score": score
        }
    
    return rankings


def calculate_build_type_combination_rankings(conn: sqlite3.Connection, equipment: Dict, build_type_statuses: list) -> Dict:
    """型内での2種ステータス組み合わせランキングを計算（新仕様）"""
    equipment_type = equipment["装備種類"]
    rarity = equipment.get("レアリティ")
    if not equipment_type or equipment_type not in STATUS_COLUMNS:
        return {}
    if not rarity:
        return {}
    
    combination_rankings = {}
    
    status_cols = STATUS_COLUMNS[equipment_type]
    active_statuses = {
        col for col in status_cols
        if pd.notna(equipment.get(col)) and equipment.get(col) not in [None, 0]
    }

    offense_stats = {"攻撃力", "会心率", "命中率"}
    defense_stats = {"体力", "防御力", "回避率"}

    type_pairs = {
        "襲撃編成型": [pair for pair in combinations(sorted(active_statuses & offense_stats), 2)],
        "迎撃編成耐久型": [pair for pair in combinations(sorted(active_statuses & defense_stats), 2)],
        "迎撃編成撃退型": []
    }

    if {"防御力", "命中率"}.issubset(active_statuses):
        type_pairs["迎撃編成撃退型"].append(("防御力", "命中率"))
    if {"防御力", "会心率"}.issubset(active_statuses):
        type_pairs["迎撃編成撃退型"].append(("防御力", "会心率"))

    for build_type, pairs in type_pairs.items():
        for status1, status2 in pairs:
            try:
                val1 = float(equipment.get(status1, 0) or 0)
                val2 = float(equipment.get(status2, 0) or 0)
            except (ValueError, TypeError):
                continue

            df = pd.read_sql(f"""
                SELECT {status1}, {status2}, 装備名, レアリティ
                FROM mart_equipments_master
                WHERE 装備種類 = ?
                AND レアリティ = ?
                AND {status1} IS NOT NULL AND {status1} > 0
                AND {status2} IS NOT NULL AND {status2} > 0
            """, conn, params=(equipment_type, rarity))

            if df.empty:
                continue

            min1, max1 = df[status1].min(), df[status1].max()
            min2, max2 = df[status2].min(), df[status2].max()

            score1 = 100.0 if max1 == min1 else 100.0 * (val1 - min1) / (max1 - min1)
            score2 = 100.0 if max2 == min2 else 100.0 * (val2 - min2) / (max2 - min2)
            combo_score = (score1 + score2) / 2

            df = df.copy()
            df["s1"] = 100.0 if max1 == min1 else 100.0 * (df[status1] - min1) / (max1 - min1)
            df["s2"] = 100.0 if max2 == min2 else 100.0 * (df[status2] - min2) / (max2 - min2)
            df["combo_score"] = (df["s1"] + df["s2"]) / 2

            total_count = len(df)
            rank = (df["combo_score"] > combo_score).sum() + 1
            diff = df["combo_score"].max() - combo_score

            combo_key = f"{build_type}:{status1}・{status2}"
            combination_rankings[combo_key] = {
                "rank": int(rank),
                "total": int(total_count),
                "diff": float(diff),
                "value": float(val1 + val2),
                "score": float(combo_score),
                "statuses": [status1, status2],
                "build_type": build_type,
                "combo_name": f"{status1}・{status2}",
            }
    
    return combination_rankings


def analyze_build_type(equipment: Dict, rankings: Dict) -> tuple:
    """
    ビルドタイプを判定
    
    判定順序:
    1. 迎撃編成撃退型: 防御力+命中率、または防御力+会心率
    2. 襲撃編成型: 攻撃力・会心率・命中率のうち2種以上
    3. 迎撃編成耐久型: 体力・防御力・回避率のうち2種以上
    4. 上位5位以内のステータスがあれば表示、なければ「なし」
    """
    equipment_type = equipment.get("装備種類")
    if not equipment_type or equipment_type not in STATUS_COLUMNS:
        return ("", [])
    
    status_cols = STATUS_COLUMNS[equipment_type]
    
    # 0でない・NaNでないステータスをカウント
    active_statuses = {
        col: equipment[col] for col in status_cols 
        if pd.notna(equipment.get(col)) and equipment[col] != 0
    }
    
    if len(active_statuses) == 0:
        return ("", [])
    
    status_names = set(active_statuses.keys())
    
    # 攻撃/防御ステータスの定義
    offense_stats = {"攻撃力", "会心率", "命中率"}
    defense_stats = {"体力", "防御力", "回避率"}
    
    # 1. 迎撃編成撃退型の判定（最優先: 防御力で攻撃するため）
    if "防御力" in status_names:
        if "命中率" in status_names:
            return ("迎撃編成撃退型(防御力+命中率)", ["防御力", "命中率"])
        elif "会心率" in status_names:
            return ("迎撃編成撃退型(防御力+会心率)", ["防御力", "会心率"])
    
    # 2. 襲撃編成型の判定（攻撃力・会心率・命中率のうち2種以上）
    offense_count = len(status_names & offense_stats)
    if offense_count >= 2:
        offense_list_sorted = sorted(status_names & offense_stats)
        offense_display = "・".join(offense_list_sorted)
        return (f"襲撃編成型({offense_display})", offense_list_sorted)
    
    # 3. 迎撃編成耐久型の判定（体力・防御力・回避率のうち2種以上）
    defense_count = len(status_names & defense_stats)
    if defense_count >= 2:
        defense_list_sorted = sorted(status_names & defense_stats)
        defense_display = "・".join(defense_list_sorted)
        return (f"迎撃編成耐久型({defense_display})", defense_list_sorted)
    
    # 4. その他: 単一ステータスまたはその他の組み合わせ
    # 上位5位以内のステータスがあるかチェック
    top5_statuses = [stat for stat, data in rankings.items() if data["rank"] <= 5]
    
    if top5_statuses:
        # 上位5位のステータス名を表示
        top5_sorted = sorted(top5_statuses)
        top5_display = "・".join(top5_sorted)
        return (f"上位型({top5_display})", top5_sorted)
    
    return ("", [])


def calculate_overall_status_score(rankings: Dict, build_type_rankings: Dict = None) -> tuple:
    """総合ステータススコアを計算（平均値）"""
    if build_type_rankings:
        best = max(build_type_rankings.values(), key=lambda x: x["score"])
        return (best["score"], f'{best["build_type"]} ({best["combo_name"]})')

    if not rankings:
        return (0.0, "")
    
    # 各ステータススコアの平均値
    scores = [data["score"] for data in rankings.values()]
    avg_score = sum(scores) / len(scores)
    
    return (avg_score, "平均値")


def export_to_excel(output_path: str = "mock_評価/mart_with_scores.xlsx"):
    """mart_equipments_masterをスコア付きでExcelにエクスポート"""
    conn = sqlite3.connect(DB_FILE)
    
    # mart_equipments_masterを読み込む
    df = pd.read_sql("SELECT * FROM mart_equipments_master", conn)
    
    print(f"装備データ読み込み: {len(df)}件")
    
    # スコア列を追加
    status_scores = []
    status_score_types = []
    ability_scores = []
    build_types = []
    
    # 詳細スコア用の列
    detail_cols = {
        '体力_rank': [], '体力_total': [], '体力_score': [],
        '攻撃力_rank': [], '攻撃力_total': [], '攻撃力_score': [],
        '防御力_rank': [], '防御力_total': [], '防御力_score': [],
        '会心率_rank': [], '会心率_total': [], '会心率_score': [],
        '回避率_rank': [], '回避率_total': [], '回避率_score': [],
        '命中率_rank': [], '命中率_total': [], '命中率_score': [],
        'ステータス数': [],
        'ランクイン数_5位以内': [],
        'ランクイン数_10位以内': [],
        '最高ステータススコア': [],
        '平均ステータススコア': [],
        'アビリティ_重要度': [],
        'アビリティ_希少性': [],
        'アビリティ_発動条件': [],
        'アビリティ_効果係数': [],
        'アビリティ_効果量': [],
    }
    
    for idx, row in df.iterrows():
        equipment = row.to_dict()
        
        # ステータスランキング計算
        rankings = calculate_status_rankings(conn, equipment)
        build_type, build_type_statuses = analyze_build_type(equipment, rankings)
        build_type_rankings = calculate_build_type_combination_rankings(
            conn, equipment, build_type_statuses
        )

        if build_type_rankings:
            best_build = max(build_type_rankings.values(), key=lambda x: x["score"])
            build_type = f'{best_build["build_type"]}({best_build["combo_name"]})'
        
        status_score, score_type = calculate_overall_status_score(rankings, build_type_rankings)
        
        # 詳細スコアを記録
        all_stats = ['体力', '攻撃力', '防御力', '会心率', '回避率', '命中率']
        stat_scores = []
        rank5_count = 0
        rank10_count = 0
        
        for stat in all_stats:
            if stat in rankings:
                detail_cols[f'{stat}_rank'].append(rankings[stat]['rank'])
                detail_cols[f'{stat}_total'].append(rankings[stat]['total'])
                detail_cols[f'{stat}_score'].append(rankings[stat]['score'])
                stat_scores.append(rankings[stat]['score'])
                if rankings[stat]['rank'] <= 5:
                    rank5_count += 1
                if rankings[stat]['rank'] <= 10:
                    rank10_count += 1
            else:
                detail_cols[f'{stat}_rank'].append(None)
                detail_cols[f'{stat}_total'].append(None)
                detail_cols[f'{stat}_score'].append(None)
        
        detail_cols['ステータス数'].append(len(stat_scores))
        detail_cols['ランクイン数_5位以内'].append(rank5_count)
        detail_cols['ランクイン数_10位以内'].append(rank10_count)
        detail_cols['最高ステータススコア'].append(max(stat_scores) if stat_scores else 0)
        detail_cols['平均ステータススコア'].append(sum(stat_scores) / len(stat_scores) if stat_scores else 0)
        
        # アビリティスコア計算
        ability_text = equipment.get("アビリティ", "")
        ability_category = equipment.get("アビリティカテゴリ", "")
        equipment_type = equipment.get("装備種類", "")
        
        if ability_text and ability_category and equipment_type:
            from ability_evaluator import evaluate_ability
            ability_result = evaluate_ability(
                ability_text,
                ability_category,
                equipment_type,
                equipment_name=equipment.get("装備名"),
                rarity=equipment.get("レアリティ"),
            )
            ability_score = ability_result["score"]
            detail_cols['アビリティ_重要度'].append(ability_result.get("importance", 0))
            detail_cols['アビリティ_希少性'].append(ability_result.get("rarity", 0))
            detail_cols['アビリティ_発動条件'].append(ability_result.get("condition_rate", 0))
            detail_cols['アビリティ_効果係数'].append(ability_result.get("effect_weight", 1.0))
            detail_cols['アビリティ_効果量'].append(ability_result.get("effect_score", 0))
        else:
            ability_score = 0.0
            detail_cols['アビリティ_重要度'].append(0)
            detail_cols['アビリティ_希少性'].append(0)
            detail_cols['アビリティ_発動条件'].append(0)
            detail_cols['アビリティ_効果係数'].append(0)
            detail_cols['アビリティ_効果量'].append(0)
        
        status_scores.append(status_score)
        status_score_types.append(score_type)
        ability_scores.append(ability_score)
        build_types.append(build_type)
        
        if (idx + 1) % 100 == 0:
            print(f"処理中... {idx + 1}/{len(df)}")
    
    # スコア列を追加
    df["ステータススコア"] = status_scores
    df["ステータス評価種別"] = status_score_types
    df["アビリティスコア"] = ability_scores
    df["ビルドタイプ"] = build_types
    
    # 詳細列を追加
    for col_name, values in detail_cols.items():
        df[col_name] = values
    
    # Excelに出力
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='mart_with_scores', index=False)
    
    conn.close()
    print(f"\nExcelファイル出力完了: {output_path}")
    print(f"総装備数: {len(df)}件")
    print(f"ステータススコア平均: {sum(status_scores)/len(status_scores):.2f}")
    print(f"アビリティスコア平均: {sum(ability_scores)/len(ability_scores):.2f}")


if __name__ == "__main__":
    export_to_excel()
