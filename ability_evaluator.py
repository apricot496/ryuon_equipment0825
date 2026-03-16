"""
アビリティ評価モジュール
アビリティの発動条件、効果量、希少性から総合評価を計算
"""
import re
import sqlite3
from typing import Dict, List, Optional, Tuple

DB_FILE = "equipment.db"

# カテゴリ重要度の定義（100点満点）
CATEGORY_IMPORTANCE = {
    # 100点（最重要）
    "BSCT加速": 100, "BSCT進行": 100, "HACT加速": 100, "回復": 100,
    "状態異常確率上昇": 100, "状態異常付与": 100,
    "特殊効果確率上昇": 100, "特殊効果付与": 100,
    "速度上昇": 100, "ヒートゲージ上昇": 100, "会心威力上昇": 100,
    
    # 60点（重要）
    "体力上昇": 60, "攻撃力上昇": 60, "防御力上昇": 60,
    "会心率上昇": 60, "回避率上昇": 60, "命中率上昇": 60,
    "ダメージ増加": 60, "連打増幅": 60, "被状態異常確率低減": 60,
    "BS後退低減": 60, "敵BSCT減少": 60, "敵BSCT減速": 60,
    "被特殊効果確率低減": 60, "ダメージカット": 60,
    "ダメージ無効化": 60, "連打カット": 60,
    "敵ヒートゲージ増加": 60, "不死": 60,
    
    # 40点（中程度）
    "敵攻撃減少": 40, "敵防御減少": 40, "敵会心率減少": 40,
    
    # 20点（低）
    "資金獲得量上昇": 20, "敵回避率減少": 20,
    "敵速度減少": 20, "再起効果強化": 20,
}

# 発動条件の評価倍率
def evaluate_condition(ability_text: str) -> float:
    """
    発動条件から使いやすさを評価（0.5~1.0）
    """
    text = ability_text
    
    # 常時発動（条件なし）
    conditions = [
        "のとき", "以上", "以下", "持つ", "人数", "ヒートゲージ"
    ]
    if not any(cond in text for cond in conditions):
        return 1.0
    
    # 高評価条件（0.9~1.0）
    if "敵生存" in text or "敵の生存" in text:
        return 0.95
    
    if any(x in text for x in ["攻撃タイプ", "防御タイプ", "回復タイプ", "補助タイプ"]):
        return 0.9
    
    if any(x in text for x in ["組長", "東城会", "街の住人", "水商売"]):
        return 0.9
    
    # 低評価条件（0.5~0.6）
    if re.search(r"(HP|体力).+以下", text):
        return 0.55
    
    # 中評価条件（0.6~0.8）
    if any(x in text for x in ["敵", "相手"]) and "生存" not in text:
        return 0.7
    
    # その他の条件
    return 0.75


def extract_effect_value(ability_text: str, category: str) -> Optional[float]:
    """
    アビリティテキストから効果量を抽出
    """
    # 括弧内の数値がある場合は高い方を採用（例：2[6]% → 6%）
    bracket_match = re.search(r'(\d+)\[(\d+)\]%', ability_text)
    if bracket_match:
        base_value = float(bracket_match.group(1))
        bracket_value = float(bracket_match.group(2))
        return max(base_value, bracket_value)
    
    # パーセント表記を抽出（例：12%、-10%）
    # マイナス記号は表記ゆれなので無視
    percent_match = re.search(r'-?(\d+)%', ability_text)
    
    # 人数依存（例：×5%）
    if "×" in ability_text:
        multiplier_match = re.search(r'×(\d+)%', ability_text)
        if multiplier_match:
            # 5人で計算
            return float(multiplier_match.group(1)) * 5
    
    if percent_match:
        return float(percent_match.group(1))
    
    # 数値表記（攻撃力200UPなど）
    if category in ["攻撃力上昇", "攻撃力減少", "敵攻撃減少"]:
        num_match = re.search(r'(\d+)(?:UP|上昇|減少)', ability_text, re.IGNORECASE)
        if num_match:
            # 攻撃力は数値/20で%換算
            return float(num_match.group(1)) / 20
    
    if category in ["防御力上昇", "防御力減少", "敵防御減少"]:
        num_match = re.search(r'(\d+)(?:UP|上昇|減少)', ability_text, re.IGNORECASE)
        if num_match:
            # 防御力は数値/20で%換算
            return float(num_match.group(1)) / 20
    
    if category == "体力上昇":
        num_match = re.search(r'(\d+)(?:UP|上昇)', ability_text, re.IGNORECASE)
        if num_match:
            # 体力は数値のまま
            return float(num_match.group(1))
    
    return None


def calculate_category_rarity(category: str, equipment_type: str) -> float:
    """
    カテゴリの希少性を計算（0~100）
    同じ装備種類内で、同じカテゴリを持つ装備が少ないほど高得点
    """
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    # 同じ装備種類内で同じカテゴリの装備数を取得
    cur.execute("""
        SELECT COUNT(*) 
        FROM mart_equipments_master 
        WHERE アビリティカテゴリ = ? AND 装備種類 = ?
    """, (category, equipment_type))
    count = cur.fetchone()[0]
    conn.close()
    
    # 装備数が少ないほど高得点（最大100点）
    # 1個: 100点、10個: 50点、50個以上: 0点
    if count == 0:
        return 100
    elif count <= 10:
        return 100 - (count - 1) * 5.0
    elif count <= 50:
        return 50 - (count - 10) * 1.25
    else:
        return 0


def calculate_effect_rank(ability_text: str, category: str, equipment_type: str) -> float:
    """
    同じ装備種類内、同じカテゴリ内での効果量ランクを計算（0.5~1.0）
    """
    effect_value = extract_effect_value(ability_text, category)
    if effect_value is None:
        return 0.75  # デフォルト値
    
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    # 同じ装備種類内で同じカテゴリの全装備の効果量を取得
    cur.execute("""
        SELECT アビリティ 
        FROM mart_equipments_master 
        WHERE アビリティカテゴリ = ? AND 装備種類 = ? AND アビリティ IS NOT NULL
    """, (category, equipment_type))
    
    values = []
    for row in cur.fetchall():
        val = extract_effect_value(row[0], category)
        if val is not None:
            values.append(val)
    
    conn.close()
    
    if not values or len(values) == 1:
        return 1.0
    
    max_val = max(values)
    min_val = min(values)
    
    if max_val == min_val:
        return 1.0
    
    # 効果量ランク = 0.5 + (自分 - 最低) / (最高 - 最低) * 0.5
    rank = 0.5 + (effect_value - min_val) / (max_val - min_val) * 0.5
    return min(max(rank, 0.5), 1.0)


def evaluate_ability(ability_text: str, category: str, equipment_type: str) -> Dict:
    """
    アビリティの総合評価を計算
    評価点 = max(カテゴリ希少性, カテゴリ重要度) × 条件倍率 × 効果量ランク
    
    Args:
        ability_text: アビリティテキスト
        category: アビリティカテゴリ (複数カテゴリの場合はカンマ区切り)
        equipment_type: 装備種類 (武器/防具/装飾)
    """
    if not ability_text or not category or category == "なし" or category == "":
        return {
            "score": 0,
            "rarity": 0,
            "importance": 0,
            "condition_rate": 0,
            "effect_rank": 0,
            "effect_value": None,
            "categories": []
        }
    
    # 複数カテゴリの場合は分割して評価
    categories = [c.strip() for c in re.split(r'[,，＋]', category) if c.strip()]
    
    if not categories:
        return {
            "score": 0,
            "rarity": 0,
            "importance": 0,
            "condition_rate": 0,
            "effect_rank": 0,
            "effect_value": None,
            "categories": []
        }
    
    # 各カテゴリで評価して平均を取る
    category_scores = []
    all_rarities = []
    all_importances = []
    all_effect_ranks = []
    
    for cat in categories:
        rarity = calculate_category_rarity(cat, equipment_type)
        importance = CATEGORY_IMPORTANCE.get(cat, 60)
        condition_rate = evaluate_condition(ability_text)
        effect_rank = calculate_effect_rank(ability_text, cat, equipment_type)
        
        # 希少性と重要度の高い方を採用
        base_score = max(rarity, importance)
        cat_score = base_score * condition_rate * effect_rank
        
        category_scores.append(cat_score)
        all_rarities.append(rarity)
        all_importances.append(importance)
        all_effect_ranks.append(effect_rank)
    
    # 平均値を計算
    avg_score = sum(category_scores) / len(category_scores)
    avg_rarity = sum(all_rarities) / len(all_rarities)
    avg_importance = sum(all_importances) / len(all_importances)
    avg_effect_rank = sum(all_effect_ranks) / len(all_effect_ranks)
    condition_rate = evaluate_condition(ability_text)
    
    # 効果値は最初のカテゴリで抽出
    effect_value = extract_effect_value(ability_text, categories[0])
    
    return {
        "score": round(avg_score, 2),
        "rarity": round(avg_rarity, 2),
        "importance": round(avg_importance, 2),
        "condition_rate": round(condition_rate, 2),
        "effect_rank": round(avg_effect_rank, 2),
        "effect_value": effect_value,
        "categories": categories
    }


def format_ability_evaluation(ability_text: str, category: str, equipment_type: str) -> str:
    """
    アビリティ評価を読みやすいテキストに整形
    
    Args:
        ability_text: アビリティテキスト
        category: アビリティカテゴリ (複数カテゴリの場合はカンマ区切り)
        equipment_type: 装備種類 (武器/防具/装飾)
    """
    eval_result = evaluate_ability(ability_text, category, equipment_type)
    
    if eval_result["score"] == 0:
        return "アビリティなし"
    
    text = f"### アビリティ評価\n\n"
    
    # 複数カテゴリの場合は表示
    if len(eval_result.get("categories", [])) > 1:
        text += f"**カテゴリ**: {', '.join(eval_result['categories'])} (複数カテゴリの平均評価)\n\n"
    
    text += f"**総合評価点**: {eval_result['score']:.1f}点\n\n"
    text += f"- カテゴリ希少性: {eval_result['rarity']:.1f}点\n"
    text += f"- カテゴリ重要度: {eval_result['importance']}点\n"
    text += f"- 発動条件倍率: {eval_result['condition_rate']:.2f}倍\n"
    text += f"- 効果量ランク: {eval_result['effect_rank']:.2f}\n"
    
    if eval_result['effect_value']:
        text += f"- 抽出された効果量: {eval_result['effect_value']:.1f}\n"
    
    text += "\n"
    
    # 評価コメント（100点満点基準）
    score = eval_result['score']
    if score >= 80:
        text += "🌟 **非常に優秀なアビリティ**\n"
    elif score >= 60:
        text += "⭐ **優秀なアビリティ**\n"
    elif score >= 40:
        text += "✨ **実用的なアビリティ**\n"
    else:
        text += "📝 **状況次第で有用**\n"
    
    return text
