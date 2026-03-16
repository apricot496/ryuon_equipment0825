"""
装備評価ファイル生成スクリプト
ステータス評価とアビリティ評価を含むHTMLファイルを作成
"""
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, List
from ability_evaluator import format_ability_evaluation
from itertools import combinations
import asyncio
from playwright.async_api import async_playwright

DB_FILE = "equipment.db"
OUTPUT_DIR = Path("evaluation_sheets")
IMAGE_DIR = OUTPUT_DIR / "images"

# 評価対象のステータスカラム
# データベースに存在するカラム: 装備名, 装備番号, レアリティ, 体力, 攻撃力, 防御力, 会心率, 回避率, 命中率, アビリティ, アビリティカテゴリ, 装備種類
STATUS_COLUMNS = {
    "武器": ["体力", "攻撃力", "防御力", "会心率", "回避率", "命中率"],
    "防具": ["体力", "攻撃力", "防御力", "会心率", "回避率", "命中率"],
    "装飾": ["体力", "攻撃力", "防御力", "会心率", "回避率", "命中率"]
}


def get_equipment_data(conn: sqlite3.Connection, equipment_name: str, rarity: str) -> Dict:
    """
    指定された装備のデータを取得
    
    優先順位：
    1. mart_equipments_masterにある場合はそちらを使用（完全なデータ）
    2. equipment_img_scrapingのみにある場合はそちらを使用（装備種類などは不明）
    """
    cur = conn.cursor()
    
    # まずmart_equipments_masterから取得を試みる
    cur.execute("""
        SELECT 
            m.*,
            s.URL_Number,
            s.IMG_URL,
            s.画像名
        FROM mart_equipments_master m
        LEFT JOIN equipment_img_scraping s 
            ON m.装備名 = s.装備名 AND m.レアリティ = s.レアリティ
        WHERE m.装備名 = ? AND m.レアリティ = ?
    """, (equipment_name, rarity))
    
    row = cur.fetchone()
    if row:
        columns = [d[0] for d in cur.description]
        return dict(zip(columns, row))
    
    # mart_equipments_masterになければ、equipment_img_scrapingから取得
    cur.execute("""
        SELECT 
            装備名,
            レアリティ,
            体力,
            攻撃力,
            防御力,
            会心率,
            回避率,
            命中率,
            アビリティ,
            URL_Number,
            IMG_URL,
            画像名,
            NULL as 装備種類,
            NULL as アビリティカテゴリ,
            NULL as 装備番号
        FROM equipment_img_scraping
        WHERE 装備名 = ? AND レアリティ = ?
    """, (equipment_name, rarity))
    
    row = cur.fetchone()
    if not row:
        return None
    
    columns = [d[0] for d in cur.description]
    return dict(zip(columns, row))


def calculate_status_rankings(conn: sqlite3.Connection, equipment: Dict) -> Dict:
    """同装備種類内でのステータスランキングを計算"""
    equipment_type = equipment["装備種類"]
    status_cols = STATUS_COLUMNS.get(equipment_type, [])
    
    rankings = {}
    
    for status in status_cols:
        # 装備種類内での全装備のステータスを取得
        df = pd.read_sql(f"""
            SELECT {status}, 装備名, レアリティ
            FROM mart_equipments_master
            WHERE 装備種類 = ? AND {status} IS NOT NULL AND {status} > 0
            ORDER BY {status} DESC
        """, conn, params=(equipment_type,))
        
        if df.empty or equipment[status] is None or equipment[status] == 0:
            continue
        
        # ランキング計算
        total_count = len(df)
        current_value = float(equipment[status])
        rank = (df[status] > current_value).sum() + 1
        top_value = df[status].iloc[0]
        diff = top_value - current_value
        
        # スコア計算（1位=100点、最下位=50点）
        if total_count == 1:
            score = 100.0
        else:
            score = 100.0 - ((rank - 1) / (total_count - 1)) * 50.0
        
        rankings[status] = {
            "rank": rank,
            "total": total_count,
            "diff": diff,
            "value": current_value,
            "score": score
        }
    
    return rankings


def calculate_build_type_combination_rankings(conn: sqlite3.Connection, equipment: Dict, build_type_statuses: List[str]) -> Dict:
    """
    型内での2種ステータス組み合わせランキングを計算
    
    Args:
        conn: データベース接続
        equipment: 装備データ
        build_type_statuses: 型に含まれるステータスのリスト
    
    Returns:
        各組み合わせでのランキング情報
    """
    equipment_type = equipment["装備種類"]
    combination_rankings = {}
    
    # 2種類の組み合わせを生成
    for status_pair in combinations(build_type_statuses, 2):
        status1, status2 = status_pair
        
        # 両方のステータスを持つ装備のみを対象
        if equipment.get(status1) and equipment[status1] > 0 and equipment.get(status2) and equipment[status2] > 0:
            # 合計値でランキング
            df = pd.read_sql(f"""
                SELECT {status1}, {status2}, 
                       ({status1} + {status2}) as total,
                       装備名, レアリティ
                FROM mart_equipments_master
                WHERE 装備種類 = ? 
                AND {status1} IS NOT NULL AND {status1} > 0
                AND {status2} IS NOT NULL AND {status2} > 0
                ORDER BY total DESC
            """, conn, params=(equipment_type,))
            
            if not df.empty:
                current_total = float(equipment[status1]) + float(equipment[status2])
                total_count = len(df)
                rank = (df['total'] > current_total).sum() + 1
                top_value = df['total'].iloc[0]
                diff = top_value - current_total
                
                # スコア計算
                if total_count == 1:
                    score = 100.0
                else:
                    score = 100.0 - ((rank - 1) / (total_count - 1)) * 50.0
                
                combo_key = f"{status1}・{status2}"
                combination_rankings[combo_key] = {
                    "rank": rank,
                    "total": total_count,
                    "diff": diff,
                    "value": current_total,
                    "score": score,
                    "statuses": [status1, status2]
                }
    
    return combination_rankings


def analyze_build_type(equipment: Dict, rankings: Dict) -> Tuple[str, List[str]]:
    """
    ステータス組み合わせを分析してビルドタイプを判定
    
    Returns:
        (型名, 型に含まれるステータスのリスト)
    """
    equipment_type = equipment["装備種類"]
    status_cols = STATUS_COLUMNS.get(equipment_type, [])
    
    # 0でないステータスをカウント
    active_statuses = {
        col: equipment[col] for col in status_cols 
        if equipment.get(col) and equipment[col] > 0
    }
    
    if len(active_statuses) == 0:
        return ("", [])
    
    status_names = set(active_statuses.keys())
    
    # 攻撃/防御ステータスの定義
    offense_stats = {"攻撃力", "会心率", "命中率"}
    defense_stats = {"体力", "防御力", "回避率"}
    
    # 1. 迎撃編成撃退型の判定 (防御力 + 命中率 or 会心率)
    if "防御力" in status_names:
        if "命中率" in status_names:
            return ("⚔️ 迎撃編成撃退型 (防御力+命中率)", ["防御力", "命中率"])
        elif "会心率" in status_names:
            return ("⚔️ 迎撃編成撃退型 (防御力+会心率)", ["防御力", "会心率"])
    
    # 2. 襲撃編成型の判定 (攻撃力、会心率、命中率のうち2種以上)
    offense_count = len(status_names & offense_stats)
    if offense_count >= 2:
        offense_list_sorted = sorted(status_names & offense_stats)
        offense_display = "・".join(offense_list_sorted)
        return (f"⚡ 襲撃編成型 ({offense_display})", offense_list_sorted)
    
    # 3. 迎撃編成耐久型の判定 (体力、防御力、回避率のうち2種以上)
    defense_count = len(status_names & defense_stats)
    if defense_count >= 2:
        defense_list_sorted = sorted(status_names & defense_stats)
        defense_display = "・".join(defense_list_sorted)
        return (f"🛡️ 迎撃編成耐久型 ({defense_display})", defense_list_sorted)
    
    # 4. その他: 上位5位以内で判定
    top5_statuses = {stat for stat, data in rankings.items() if data["rank"] <= 5}
    
    if not top5_statuses:
        return ("", [])  # 上位5位以内のステータスがない場合は評価なし
    
    # 上位5位以内のステータスで判定
    if top5_statuses & offense_stats:
        top_offense_sorted = sorted(top5_statuses & offense_stats)
        top_offense_display = "・".join(top_offense_sorted)
        return (f"⚡ 襲撃編成型 ({top_offense_display})", top_offense_sorted)
    elif top5_statuses & defense_stats:
        top_defense_sorted = sorted(top5_statuses & defense_stats)
        top_defense_display = "・".join(top_defense_sorted)
        return (f"🛡️ 迎撃編成型 ({top_defense_display})", top_defense_sorted)
    
    return ("", [])


def calculate_overall_status_score(rankings: Dict, build_type_rankings: Dict = None) -> Tuple[float, str]:
    """
    総合ステータススコアを計算（最高値適用）
    
    Returns:
        (スコア, 評価種別: "同装備種類内評価" or "型内評価")
    """
    if not rankings:
        return (0.0, "")
    
    # 同装備種類内評価：各ステータススコアの最高値
    base_score = max([data["score"] for data in rankings.values()])
    best_score = base_score
    best_type = "同装備種類内評価"
    
    # 型内評価：組み合わせランキングの最高値
    if build_type_rankings:
        type_score = max([data["score"] for data in build_type_rankings.values()])
        if type_score > best_score:
            best_score = type_score
            best_type = "型内評価"
    
    return (best_score, best_type)


def find_superior_equipment(conn: sqlite3.Connection, equipment: Dict, ability_score: float) -> Dict:
    """
    上位互換装備を検索
    
    条件：
    - 同じ装備種類
    - 全てのステータス値が同等以上
    - かつ、アビリティスコアが高いか任意のステータスが上
    
    Returns:
        {
            'status_superior': ステータス上位互換（1件、なければNone）,
            'ability_superior': アビリティ上位互換（1件、なければNone）
        }
    """
    equipment_type = equipment['装備種類']
    
    # ステータスカラムを取得
    status_cols = STATUS_COLUMNS.get(equipment_type, [])
    if not status_cols:
        return {'status_superior': None, 'ability_superior': None}
    
    # 現装備のステータス値を取得
    current_stats = {}
    for col in status_cols:
        val = equipment.get(col)
        if val is None or (isinstance(val, str) and val.strip() == ''):
            current_stats[col] = 0
        else:
            try:
                current_stats[col] = float(val)
            except (ValueError, TypeError):
                current_stats[col] = 0
    
    # 同装備種類の全装備を取得
    query = """
    SELECT 
        m.*,
        s.URL_Number,
        s.画像名 AS img_name,
        s.IMG_URL AS img_url
    FROM mart_equipments_master m
    LEFT JOIN equipment_img_scraping s ON m.装備名 = s.装備名 AND m.レアリティ = s.レアリティ
    WHERE m.装備種類 = ?
    AND NOT (m.装備名 = ? AND m.レアリティ = ?)
    """
    
    cursor = conn.cursor()
    cursor.execute(query, (equipment_type, equipment['装備名'], equipment['レアリティ']))
    
    status_superior_list = []
    ability_superior_list = []
    
    for row in cursor.fetchall():
        # 辞書形式に変換
        columns = [desc[0] for desc in cursor.description]
        candidate = dict(zip(columns, row))
        
        # ステータス比較
        candidate_stats = {}
        has_higher_stat = False
        all_equal_or_higher = True
        
        for col in status_cols:
            val = candidate.get(col)
            if val is None or (isinstance(val, str) and val.strip() == ''):
                candidate_stats[col] = 0
            else:
                try:
                    candidate_stats[col] = float(val)
                except (ValueError, TypeError):
                    candidate_stats[col] = 0
            
            # 比較
            if candidate_stats[col] < current_stats[col]:
                all_equal_or_higher = False
                break
            elif candidate_stats[col] > current_stats[col]:
                has_higher_stat = True
        
        if not all_equal_or_higher:
            continue
        
        # アビリティスコアを計算
        from ability_evaluator import evaluate_ability
        candidate_ability_score = 0
        abilities = []
        
        # アビリティを取得（単一カラム）
        ability_text = candidate.get('アビリティ')
        if ability_text and ability_text.strip() and ability_text != "なし":
            ability_category = candidate.get('アビリティカテゴリ', 'なし')
            if ability_category and ability_category != "なし":
                ability_eval = evaluate_ability(ability_text, ability_category, equipment_type)
                candidate_ability_score = ability_eval.get('score', 0)
                abilities.append(ability_text)
        
        # URL取得（JOINで取得した画像情報を優先）
        image_url = candidate.get('img_url')  # JOINで取得したIMG_URL
        
        # IMG_URLがない場合、画像名から生成
        if not image_url:
            img_name = candidate.get('img_name')  # JOINで取得した画像名
            if img_name:
                image_url = f"https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/main/static/{img_name}"
        
        # ステータス合計値
        stats_total = sum(candidate_stats.values())
        
        item_data = {
            'equipment': candidate,
            'ability_score': candidate_ability_score,
            'stats_total': stats_total,
            'stats': candidate_stats,
            'image_url': image_url,
            'abilities': abilities
        }
        
        # ステータスが上位
        if has_higher_stat:
            status_superior_list.append(item_data)
        
        # アビリティスコアが上位
        if candidate_ability_score > ability_score:
            ability_superior_list.append(item_data)
    
    # ステータス上位互換：ステータス合計値が最も高いもの
    status_superior = None
    if status_superior_list:
        status_superior_list.sort(key=lambda x: x['stats_total'], reverse=True)
        status_superior = status_superior_list[0]
    
    # アビリティ上位互換：アビリティスコアが最も高いもの
    ability_superior = None
    if ability_superior_list:
        ability_superior_list.sort(key=lambda x: x['ability_score'], reverse=True)
        ability_superior = ability_superior_list[0]
    
    return {
        'status_superior': status_superior,
        'ability_superior': ability_superior
    }


def generate_evaluation_html(conn: sqlite3.Connection, equipment_name: str, rarity: str) -> Tuple[str, int]:
    """装備評価のHTMLを生成（2カラムレイアウト）。戻り値: (HTML文字列, URL_Number)"""
    equipment = get_equipment_data(conn, equipment_name, rarity)
    
    if not equipment:
        return None, None
    
    # URLを取得（URL_Number=0は除外）
    url_number = equipment.get("URL_Number", "")
    # URL_Numberが0または空文字列の場合はURLを生成しない
    if url_number and str(url_number) != "0" and url_number != 0:
        url = f"https://ryu.sega-online.jp/news/{url_number}/"
    else:
        url = ""
    
    # GitHub画像URL
    img_name = equipment.get("画像名", "")
    img_url = equipment.get("IMG_URL", "")
    if not img_url and img_name:
        img_url = f"https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/main/static/{img_name}"
    
    # ステータス文字列を作成
    equipment_type = equipment["装備種類"]
    status_cols = STATUS_COLUMNS.get(equipment_type, [])
    status_lines = []
    for col in status_cols:
        if equipment.get(col) and equipment[col] > 0:
            val = equipment[col]
            if isinstance(val, float) and val != int(val):
                status_lines.append(f"{col}: {val:.1f}")
            else:
                status_lines.append(f"{col}: {int(val)}")
    status_str = "<br>".join(status_lines) if status_lines else "なし"
    
    # アビリティ
    ability = equipment.get("アビリティ", "なし") or "なし"
    
    # ステータス評価HTML
    rankings = calculate_status_rankings(conn, equipment)
    build_type_name, build_type_statuses = analyze_build_type(equipment, rankings)
    
    # 型内評価（2種以上のステータスがある場合のみ）
    build_type_rankings = {}
    if len(build_type_statuses) >= 2:
        build_type_rankings = calculate_build_type_combination_rankings(conn, equipment, build_type_statuses)
    
    status_html = ""
    if rankings:
        overall_score, score_type = calculate_overall_status_score(rankings, build_type_rankings)
        status_html += f'<h2>ステータス評価</h2>'
        status_html += f'<div class="score-box">ステータススコア: <strong>{overall_score:.1f}点</strong> ({score_type})</div>'
        
        # 装備種類名でのランキング表示
        status_html += f'<h3>{equipment_type}内でのランキング</h3><ul>'
        for status, data in rankings.items():
            status_html += f'<li>{status}: <strong>{data["rank"]}位/{data["total"]}中</strong> '
            status_html += f'<span class="score">(スコア: {data["score"]:.1f}点)</span><br>'
            status_html += f'<span class="diff">1位との差分: {data["diff"]:.1f}</span></li>'
        status_html += '</ul>'
    
    # 型内評価（存在する場合）
    if build_type_rankings:
        status_html += f'<h3>型内ステータス組み合わせランキング</h3><ul>'
        for combo_name, data in build_type_rankings.items():
            status_html += f'<li>{combo_name}: <strong>{data["rank"]}位/{data["total"]}中</strong> '
            status_html += f'<span class="score">(スコア: {data["score"]:.1f}点)</span><br>'
            status_html += f'<span class="diff">1位との差分: {data["diff"]:.1f}</span></li>'
        status_html += '</ul>'
    
    # ステータス組み合わせ評価（型）
    if build_type_name:
        status_html += f'<h3>ステータス組み合わせ評価</h3><p class="build-type">{build_type_name}</p>'
    else:
        status_html += f'<h3>ステータス組み合わせ評価</h3><p>型分類なし</p>'
    
    # アビリティ評価HTML
    ability_category = equipment.get("アビリティカテゴリ", "なし") or "なし"
    ability_html = ""
    if ability and ability != "なし" and ability_category != "なし":
        from ability_evaluator import evaluate_ability
        eval_result = evaluate_ability(ability, ability_category, equipment_type)
        
        if eval_result["score"] > 0:
            ability_html += '<h2>アビリティ評価</h2>'
            ability_html += f'<div class="score-box">アビリティスコア: <strong>{eval_result["score"]:.1f}点</strong></div>'
            
            if len(eval_result.get("categories", [])) > 1:
                ability_html += f'<p><strong>カテゴリ</strong>: {", ".join(eval_result["categories"])} (複数カテゴリの平均評価)</p>'
            
            ability_html += '<ul>'
            ability_html += f'<li>カテゴリ希少性: {eval_result["rarity"]:.1f}点</li>'
            ability_html += f'<li>カテゴリ重要度: {eval_result["importance"]}点</li>'
            ability_html += f'<li>発動条件倍率: {eval_result["condition_rate"]:.2f}倍</li>'
            ability_html += f'<li>効果量ランク: {eval_result["effect_rank"]:.2f}</li>'
            if eval_result['effect_value']:
                ability_html += f'<li>抽出された効果量: {eval_result["effect_value"]:.1f}</li>'
            ability_html += '</ul>'
            
            score = eval_result['score']
            if score >= 80:
                ability_html += '<p class="rating excellent">🌟 <strong>非常に優秀なアビリティ</strong></p>'
            elif score >= 60:
                ability_html += '<p class="rating good">⭐ <strong>優秀なアビリティ</strong></p>'
            elif score >= 40:
                ability_html += '<p class="rating practical">✨ <strong>実用的なアビリティ</strong></p>'
            else:
                ability_html += '<p class="rating situational">📝 <strong>状況次第で有用</strong></p>'
    else:
        ability_html += '<h2>アビリティ評価</h2><p>アビリティなし</p>'
    
    # 上位互換装備の検索
    total_ability_score = 0
    for i in range(1, 4):
        ability_col = f'アビリティ{i}'
        ability_text = equipment.get(ability_col)
        if ability_text and ability_text.strip() and ability_text != "なし":
            from ability_evaluator import evaluate_ability
            ability_eval = evaluate_ability(conn, ability_text, equipment['装備種類'])
            total_ability_score += ability_eval.get('score', 0)
    
    superior_data = find_superior_equipment(conn, equipment, total_ability_score)
    
    # 上位互換装備HTML
    superior_html = ""
    status_sup = superior_data.get('status_superior')
    ability_sup = superior_data.get('ability_superior')
    
    if status_sup or ability_sup:
        superior_html += '<div class="content">'
        superior_html += '<h2>🔝 上位互換装備</h2>'
        superior_html += '<p class="superior-note">全ステータス同等以上で、アビリティまたはステータスが優れている装備</p>'
        
        superior_html += '<table class="superior-table">'
        superior_html += '<thead><tr>'
        superior_html += '<th style="width: 20%;">画像</th>'
        superior_html += '<th style="width: 30%;">ステータス</th>'
        superior_html += '<th style="width: 50%;">アビリティ</th>'
        superior_html += '</tr></thead>'
        superior_html += '<tbody>'
        
        # ステータス上位互換
        if status_sup:
            sup_eq = status_sup['equipment']
            sup_name = sup_eq.get('装備名', '不明')
            sup_rarity = sup_eq.get('レアリティ', '')
            sup_image_url = status_sup['image_url'] or ''
            sup_ability_score = status_sup['ability_score']
            sup_stats = status_sup['stats']
            sup_abilities = status_sup.get('abilities', [])
            
            superior_html += '<tr>'
            
            # 画像列
            superior_html += '<td>'
            if sup_image_url:
                superior_html += f'<img src="{sup_image_url}" alt="{sup_name}" width="80">'
            superior_html += f'<div class="equipment-name-small">{sup_name}<br>({sup_rarity})</div>'
            superior_html += '</td>'
            
            # ステータス列
            superior_html += '<td class="stats-compact">'
            status_lines = []
            for stat_name, stat_value in sup_stats.items():
                if stat_value > 0:
                    if isinstance(stat_value, float) and stat_value != int(stat_value):
                        status_lines.append(f'{stat_name}: {stat_value:.1f}')
                    else:
                        status_lines.append(f'{stat_name}: {int(stat_value)}')
            superior_html += '<br>'.join(status_lines) if status_lines else 'なし'
            superior_html += '</td>'
            
            # アビリティ列
            superior_html += '<td class="ability-compact">'
            if sup_abilities:
                superior_html += f'<div class="ability-item">{sup_abilities[0]}</div>'
                superior_html += f'<div class="ability-score-small">スコア: {sup_ability_score:.1f}点</div>'
            else:
                superior_html += 'なし'
            superior_html += '</td>'
            superior_html += '</tr>'
        
        # アビリティ上位互換
        if ability_sup:
            # ステータス上位と同じ装備の場合はスキップ
            if not status_sup or ability_sup['equipment']['装備名'] != status_sup['equipment']['装備名'] or ability_sup['equipment']['レアリティ'] != status_sup['equipment']['レアリティ']:
                sup_eq = ability_sup['equipment']
                sup_name = sup_eq.get('装備名', '不明')
                sup_rarity = sup_eq.get('レアリティ', '')
                sup_image_url = ability_sup['image_url'] or ''
                sup_ability_score = ability_sup['ability_score']
                sup_stats = ability_sup['stats']
                sup_abilities = ability_sup.get('abilities', [])
                
                superior_html += '<tr>'
                
                # 画像列
                superior_html += '<td>'
                if sup_image_url:
                    superior_html += f'<img src="{sup_image_url}" alt="{sup_name}" width="80">'
                superior_html += f'<div class="equipment-name-small">{sup_name}<br>({sup_rarity})</div>'
                superior_html += '</td>'
                
                # ステータス列
                superior_html += '<td class="stats-compact">'
                status_lines = []
                for stat_name, stat_value in sup_stats.items():
                    if stat_value > 0:
                        if isinstance(stat_value, float) and stat_value != int(stat_value):
                            status_lines.append(f'{stat_name}: {stat_value:.1f}')
                        else:
                            status_lines.append(f'{stat_name}: {int(stat_value)}')
                superior_html += '<br>'.join(status_lines) if status_lines else 'なし'
                superior_html += '</td>'
                
                # アビリティ列
                superior_html += '<td class="ability-compact">'
                if sup_abilities:
                    superior_html += f'<div class="ability-item">{sup_abilities[0]}</div>'
                    superior_html += f'<div class="ability-score-small">スコア: {sup_ability_score:.1f}点</div>'
                else:
                    superior_html += 'なし'
                superior_html += '</td>'
                superior_html += '</tr>'
        
        superior_html += '</tbody></table>'
        superior_html += '</div>'  # content
    
    # HTML作成
    html = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{equipment_name} ({rarity}) 評価</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Hiragino Sans', 'Noto Sans CJK JP', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            position: relative;
            color: white;
        }}
        .meta-info {{
            position: absolute;
            top: 20px;
            right: 30px;
            text-align: right;
            font-size: 14px;
            opacity: 0.95;
        }}
        .meta-info div {{
            margin: 4px 0;
        }}
        .meta-info a {{
            color: white;
            text-decoration: none;
            border-bottom: 1px solid rgba(255,255,255,0.5);
        }}
        h1 {{
            font-size: 36px;
            font-weight: 700;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}
        .equipment-table {{
            width: 100%;
            margin: 30px;
            max-width: calc(100% - 60px);
        }}
        .equipment-table table {{
            width: 100%;
            border-collapse: collapse;
            background: #f8f9fa;
            border-radius: 8px;
            overflow: hidden;
        }}
        .equipment-table th, .equipment-table td {{
            padding: 20px;
            border: 1px solid #dee2e6;
        }}
        .equipment-table th {{
            background: #e9ecef;
            font-weight: 600;
            text-align: center;
        }}
        .equipment-table td {{
            vertical-align: middle;
        }}
        .equipment-table img {{
            display: block;
            margin: 0 auto;
            border-radius: 8px;
        }}
        .two-column {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            padding: 30px;
        }}
        .column {{
            background: #f8f9fa;
            padding: 25px;
            border-radius: 12px;
        }}
        .content {{
            padding: 30px;
        }}
        h2 {{
            color: #667eea;
            font-size: 24px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        h3 {{
            color: #555;
            font-size: 18px;
            margin: 20px 0 12px 0;
        }}
        .score-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
            font-size: 18px;
        }}
        ul {{
            list-style: none;
            padding: 0;
        }}
        li {{
            padding: 12px 0;
            border-bottom: 1px solid #e9ecef;
        }}
        li:last-child {{
            border-bottom: none;
        }}
        .score {{
            color: #667eea;
            font-weight: 600;
        }}
        .diff {{
            color: #666;
            font-size: 14px;
        }}
        .build-type {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            margin-top: 10px;
            font-size: 16px;
        }}
        .rating {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            text-align: center;
            font-size: 16px;
        }}
        .rating.excellent {{
            border-left: 4px solid #ffd700;
        }}
        .rating.good {{
            border-left: 4px solid #4CAF50;
        }}
        .rating.practical {{
            border-left: 4px solid #2196F3;
        }}
        .rating.situational {{
            border-left: 4px solid #9E9E9E;
        }}
        .superior-note {{
            color: #666;
            font-size: 14px;
            margin-bottom: 15px;
            font-style: italic;
        }}
        .superior-table {{
            width: 100%;
            border-collapse: collapse;
            background: #f8f9fa;
            border-radius: 8px;
            overflow: hidden;
            font-size: 11px;
        }}
        .superior-table th, .superior-table td {{
            padding: 10px;
            border: 1px solid #dee2e6;
        }}
        .superior-table th {{
            background: #e9ecef;
            font-weight: 600;
            text-align: center;
            font-size: 12px;
        }}
        .superior-table td {{
            vertical-align: middle;
        }}
        .superior-table img {{
            display: block;
            margin: 0 auto;
            border-radius: 4px;
        }}
        .equipment-name-small {{
            text-align: center;
            font-size: 10px;
            margin-top: 4px;
            color: #667eea;
            font-weight: 600;
            line-height: 1.3;
        }}
        .stats-compact {{
            font-size: 11px;
            line-height: 1.4;
        }}
        .ability-compact {{
            font-size: 11px;
            line-height: 1.3;
        }}
        .ability-item {{
            margin: 4px 0;
            padding: 2px 0;
        }}
        .ability-score-small {{
            color: #667eea;
            font-weight: bold;
            margin-top: 6px;
            font-size: 10px;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            color: #666;
            font-size: 14px;
            border-top: 1px solid #e9ecef;
        }}
        .footer h4 {{
            font-size: 14px;
            color: #555;
            margin-bottom: 10px;
        }}
        .footer ul {{
            font-size: 13px;
            text-align: left;
            max-width: 800px;
            margin: 10px auto;
        }}
        .footer li {{
            padding: 4px 0;
            border: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="meta-info">
                <div>更新日: {datetime.now().strftime('%Y/%m/%d')}</div>
                {"<div><a href='" + url + "' target='_blank'>" + url + "</a></div>" if url else ""}
                <div>装備種類: {equipment_type}</div>
            </div>
            <h1>{equipment_name}</h1>
        </div>
        
        <div class="equipment-table">
            <table>
                <thead>
                    <tr>
                        <th style="width: 120px;">画像</th>
                        <th>ステータス</th>
                        <th>アビリティ</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>{"<img src='" + img_url + "' width='80'>" if img_url else ""}</td>
                        <td>{status_str}</td>
                        <td>{ability}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div class="two-column">
            <div class="column">
                {status_html}
            </div>
            <div class="column">
                {ability_html}
            </div>
        </div>
        
        {superior_html}
        
        <div class="footer">
            <p><em>この評価は自動生成されたものです</em></p>
            <h4>スコア算出方法</h4>
            <ul>
                <li><strong>ステータススコア</strong>: 各ステータスの最高スコアを採用（1位=100点、最下位=50点で線形補間）</li>
                <li style="padding-left: 20px;">同装備種類内評価と型内評価の高い方を総合スコアとする</li>
                <li style="padding-left: 20px;">型内評価: 型に含まれる2種ステータス組み合わせでのランキング評価</li>
                <li><strong>アビリティスコア</strong>: max(カテゴリ希少性, カテゴリ重要度) × 発動条件倍率 × 効果量ランク</li>
                <li style="padding-left: 20px;">カテゴリ重要度: 最重要100点/重要60点/中程度40点/低20点（100点満点）</li>
                <li style="padding-left: 20px;">カテゴリ希少性: 装備数が少ないほど高得点（0-100点）</li>
                <li style="padding-left: 20px;">発動条件倍率: 無条件1.0倍、条件付き0.5〜0.9倍</li>
                <li style="padding-left: 20px;">効果量ランク: 同カテゴリ内での効果量に基づき0.5〜1.0</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""
    return html, url_number


def save_evaluation_file(equipment_name: str, rarity: str, content: str, url_number: int = None):
    """評価ファイル（HTML）を保存"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # ファイル名から不正な文字を除去
    safe_name = equipment_name.replace("/", "_").replace("\\", "_")
    
    # ファイル名に日付とURL_Numberを追加
    current_date = datetime.now().strftime("%Y%m%d")
    if url_number is not None and url_number != 0:
        filename = f"{current_date}_{url_number}_{safe_name}_{rarity}_評価.html"
    else:
        filename = f"{current_date}_0_{safe_name}_{rarity}_評価.html"
    
    filepath = OUTPUT_DIR / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"✓ 生成完了: {filepath}")
    return filepath


async def generate_preview_image_async(html_filepath: Path, output_path: Path):
    """HTMLファイルから画像を生成（非同期）"""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 1600})
        
        # ファイルパスを file:// URL に変換
        file_url = f"file://{html_filepath.absolute()}"
        await page.goto(file_url)
        
        # ページがロードされるまで待機
        await page.wait_for_load_state("networkidle")
        
        # スクリーンショット
        await page.screenshot(path=str(output_path), full_page=True)
        await browser.close()


def generate_preview_image(html_filepath: Path) -> Path:
    """HTMLファイルから画像を生成"""
    IMAGE_DIR.mkdir(exist_ok=True, parents=True)
    
    # 画像ファイルパス
    image_filename = html_filepath.stem + ".png"
    image_filepath = IMAGE_DIR / image_filename
    
    # 非同期で画像生成
    asyncio.run(generate_preview_image_async(html_filepath, image_filepath))
    
    print(f"✓ 画像生成完了: {image_filepath}")
    return image_filepath


def generate_all_evaluations(generate_images: bool = True):
    """全装備の評価ファイルを生成"""
    conn = sqlite3.connect(DB_FILE)
    
    # 全装備を取得
    df = pd.read_sql("""
        SELECT 装備名, レアリティ, 装備種類
        FROM mart_equipments_master
        ORDER BY 装備種類, レアリティ, 装備名
    """, conn)
    
    print(f"評価ファイル生成開始: {len(df)}件")
    
    success_count = 0
    error_count = 0
    image_count = 0
    
    for _, row in df.iterrows():
        equipment_name = row["装備名"]
        rarity = row["レアリティ"]
        
        try:
            content, url_number = generate_evaluation_html(conn, equipment_name, rarity)
            if content:
                html_filepath = save_evaluation_file(equipment_name, rarity, content, url_number)
                success_count += 1
                
                if generate_images:
                    try:
                        generate_preview_image(html_filepath)
                        image_count += 1
                    except Exception as e:
                        print(f"⚠ 画像生成エラー ({equipment_name}): {e}")
        except Exception as e:
            print(f"✗ エラー: {equipment_name} ({rarity}) - {e}")
            error_count += 1
    
    conn.close()
    
    print(f"\n評価ファイル生成完了!")
    print(f"  成功: {success_count}件")
    print(f"  失敗: {error_count}件")
    if generate_images:
        print(f"  画像生成: {image_count}件")


def generate_single_evaluation(equipment_name: str, rarity: str = None, generate_image: bool = True):
    """特定の装備の評価ファイルを生成"""
    conn = sqlite3.connect(DB_FILE)
    
    # レアリティ指定がない場合は全レアリティを取得
    if rarity is None:
        df = pd.read_sql("""
            SELECT レアリティ FROM mart_equipments_master
            WHERE 装備名 = ?
        """, conn, params=(equipment_name,))
        rarities = df["レアリティ"].tolist()
    else:
        rarities = [rarity]
    
    for r in rarities:
        content, url_number = generate_evaluation_html(conn, equipment_name, r)
        if content:
            html_filepath = save_evaluation_file(equipment_name, r, content, url_number)
            if generate_image:
                try:
                    generate_preview_image(html_filepath)
                except Exception as e:
                    print(f"⚠ 画像生成エラー: {e}")
        else:
            print(f"✗ 見つかりません: {equipment_name} ({r})")
    
    conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # 特定の装備を指定
        equipment_name = sys.argv[1]
        rarity = sys.argv[2] if len(sys.argv) > 2 else None
        generate_single_evaluation(equipment_name, rarity)
    else:
        # 全装備生成
        generate_all_evaluations()
