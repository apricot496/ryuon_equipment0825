"""
各装備のアビリティから最大効果値を抽出
生存人数×5% → 5人で計算 → 25%
不在人数×N% → 4人で計算 → N*4%
"""
import sqlite3
import re
from pathlib import Path
from ability_evaluator import extract_effect_value, evaluate_ability

DB_FILE = "equipment.db"
OUTPUT_FILE = "mock_評価/equipment_max_effects.csv"
OUTPUT_LONG_FILE = "mock_評価/equipment_max_effects_long.csv"
OUTPUT_SCORE_FILE = "mock_評価/equipment_ability_scores.csv"


def extract_activation_probability(ability_text: str):
    """アビリティテキストから発動確率(%)を抽出。なければNone。"""
    if not ability_text:
        return None

    text = ability_text.replace('％', '%')
    # 4[12]% のような表記は高い方を採用
    bracket_match = re.search(r'(\d+)\[(\d+)\]%の確率', text)
    if bracket_match:
        return float(max(int(bracket_match.group(1)), int(bracket_match.group(2))))

    match = re.search(r'(\d+(?:\.\d+)?)%の確率', text)
    if match:
        return float(match.group(1))
    return None

def get_all_abilities_with_max_effects():
    """全装備のアビリティと最大効果値を取得"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 装備名, レアリティ, アビリティカテゴリ, アビリティ, 装備種類
        FROM mart_equipments_master
        WHERE アビリティ IS NOT NULL AND アビリティ != ''
        ORDER BY レアリティ DESC, 装備名
    """)
    
    results = []
    for row in cur.fetchall():
        name, rarity, category, ability_text, equipment_type = row
        categories = [c.strip() for c in re.split(r'[,，＋]', category or '') if c.strip()]
        is_multi_category = len(categories) > 1

        # 複数カテゴリは一旦空欄運用
        effect_value = None if is_multi_category else extract_effect_value(ability_text, category)
        activation_probability = extract_activation_probability(ability_text)
        
        results.append({
            '装備名': name,
            'レアリティ': rarity,
            'カテゴリ': category,
            'アビリティ': ability_text,
            '抽出効果値': effect_value if effect_value is not None else '',
            '発動確率': activation_probability if activation_probability is not None else '',
            '装備種類': equipment_type
        })
    
    conn.close()
    return results


def to_long_format_rows(rows):
    """横持ち行を縦持ち（1カテゴリ=1行）に展開"""
    long_rows = []

    for row in rows:
        original_category = row.get('カテゴリ', '') or ''
        categories = [c.strip() for c in re.split(r'[,，＋]', original_category) if c.strip()]

        # カテゴリが空の場合はそのまま1行
        if not categories:
            copied = dict(row)
            copied['元カテゴリ'] = original_category
            copied['カテゴリ'] = ''
            copied['カテゴリ数'] = 0
            copied['カテゴリ連番'] = ''
            long_rows.append(copied)
            continue

        # 1カテゴリずつ行展開
        for index, single_category in enumerate(categories, start=1):
            copied = dict(row)
            copied['元カテゴリ'] = original_category
            copied['カテゴリ'] = single_category
            copied['カテゴリ数'] = len(categories)
            copied['カテゴリ連番'] = index

            # 縦持ち側は各カテゴリ単位で効果値を再抽出
            copied['抽出効果値'] = extract_effect_value(copied['アビリティ'], single_category) or ''
            long_rows.append(copied)

    return long_rows


def build_ability_score_rows():
    """
    指定フォーマットのアビリティスコア行を作成
    列: 装備名, レアリティ, 装備種類, カテゴリ, アビリティ, 重要度,
         抽出効果値, 効果量スコア, 発動確率, アビリティスコア
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT 装備名, レアリティ, 装備種類, アビリティカテゴリ, アビリティ
        FROM mart_equipments_master
        WHERE アビリティ IS NOT NULL AND アビリティ != ''
        ORDER BY レアリティ DESC, 装備名
    """)

    rows = []
    for name, rarity, equipment_type, categories, ability_text in cur.fetchall():
        if not categories or categories == "なし":
            continue

        eval_result = evaluate_ability(
            ability_text,
            categories,
            equipment_type,
            equipment_name=name,
            rarity=rarity,
        )

        rows.append({
            '装備名': name,
            'レアリティ': rarity,
            '装備種類': equipment_type,
            'カテゴリ': eval_result.get('representative_category') or categories,
            'アビリティ': ability_text,
            '重要度': eval_result.get('importance', 0),
            '抽出効果値': eval_result.get('effect_value', ''),
            '効果量スコア': eval_result.get('effect_score', 0),
            '発動確率': extract_activation_probability(ability_text) or '',
            'アビリティスコア': eval_result.get('score', 0),
        })

    conn.close()
    return rows

if __name__ == "__main__":
    results = get_all_abilities_with_max_effects()
    long_results = to_long_format_rows(results)
    score_rows = build_ability_score_rows()
    
    # CSV出力
    Path("mock_評価").mkdir(exist_ok=True)
    
    import csv
    with open(OUTPUT_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(
            f, 
            fieldnames=['装備名', 'レアリティ', '装備種類', 'カテゴリ', 'アビリティ', '抽出効果値', '発動確率']
        )
        writer.writeheader()
        writer.writerows(results)

    # 縦持ちCSV出力（1カテゴリ=1行）
    with open(OUTPUT_LONG_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                '装備名', 'レアリティ', '装備種類', '元カテゴリ', 'カテゴリ', 'カテゴリ数', 'カテゴリ連番',
                'アビリティ', '抽出効果値', '発動確率'
            ]
        )
        writer.writeheader()
        writer.writerows(long_results)

    # 指定フォーマットのスコアCSV
    with open(OUTPUT_SCORE_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                '装備名', 'レアリティ', '装備種類', 'カテゴリ', 'アビリティ',
                '重要度', '抽出効果値', '効果量スコア', '発動確率', 'アビリティスコア'
            ]
        )
        writer.writeheader()
        writer.writerows(score_rows)
    
    print(f"✓ {OUTPUT_FILE} に {len(results)} 件出力しました")
    print(f"✓ {OUTPUT_LONG_FILE} に {len(long_results)} 件出力しました")
    print(f"✓ {OUTPUT_SCORE_FILE} に {len(score_rows)} 件出力しました")
    print("\n=== サンプル (最初の15件) ===")
    for i, r in enumerate(results[:15], 1):
        print(f"{i}. {r['装備名']} ({r['レアリティ']}) [{r['装備種類']}]")
        print(f"   カテゴリ: {r['カテゴリ']}")
        print(f"   アビリティ: {r['アビリティ']}")
        print(f"   抽出効果値: {r['抽出効果値']}")
        print()
