"""
アビリティ評価モジュール
アビリティの発動条件・カテゴリ重要度・効果量スコアから総合評価を計算
"""
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_FILE = "equipment.db"
CATEGORY_SETTINGS_FILE = Path("mock_評価/ability_category_settings.csv")

# カテゴリ重要度（ユーザー指定）
CATEGORY_IMPORTANCE = {
    "BSCT加速": 100,
    "BSCT進行": 100,
    "BS後退低減": 100,
    "HACT加速": 100,
    "ダメージカット": 80,
    "ダメージ増加": 80,
    "ダメージ無効化": 80,
    "ヒートゲージ上昇": 100,
    "不死": 90,
    "会心威力上昇": 100,
    "会心率上昇": 100,
    "体力上昇": 60,
    "再起効果強化": 50,
    "命中率上昇": 100,
    "回復": 100,
    "回避率上昇": 90,
    "攻撃力上昇": 100,
    "敵BSCT減少": 80,
    "敵BSCT減速": 80,
    "敵ヒートゲージ増加": 100,
    "敵会心率減少": 50,
    "敵回避率減少": 50,
    "敵攻撃減少": 50,
    "敵速度減少": 50,
    "敵防御減少": 50,
    "特殊効果付与": 100,
    "特殊効果確率上昇": 100,
    "状態異常付与": 100,
    "状態異常確率上昇": 100,
    "被特殊効果確率低減": 100,
    "被状態異常確率低減": 100,
    "資金獲得量上昇": 0,
    "速度上昇": 100,
    "連打カット": 50,
    "連打増幅": 50,
    "防御力上昇": 60,
}

# カテゴリ効果係数（初期値）
# 効果量ランクに乗算して最終効果ランクを調整する
CATEGORY_EFFECT_WEIGHT = {key: 1.0 for key in CATEGORY_IMPORTANCE.keys()}

_CATEGORY_SETTINGS_CACHE = None


def _to_float_or_none(value) -> Optional[float]:
    """文字列/数値をfloatに変換。変換不可ならNone"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if text == "":
        return None

    # 末尾%などのノイズを除去
    text = text.replace("%", "")

    try:
        return float(text)
    except ValueError:
        return None


def _load_category_settings() -> Dict[str, Dict[str, float]]:
    """
    カテゴリ設定CSVを読み込む

    許容ヘッダ:
    - カテゴリ / category
    - 重要度 / importance
    - 効果係数 / effect_weight
    """
    global _CATEGORY_SETTINGS_CACHE

    if _CATEGORY_SETTINGS_CACHE is not None:
        return _CATEGORY_SETTINGS_CACHE

    settings: Dict[str, Dict[str, float]] = {}

    if not CATEGORY_SETTINGS_FILE.exists():
        _CATEGORY_SETTINGS_CACHE = settings
        return settings

    import csv

    with CATEGORY_SETTINGS_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = (row.get("カテゴリ") or row.get("category") or "").strip()
            if not category:
                continue

            importance = _to_float_or_none(row.get("重要度") or row.get("importance"))
            effect_weight = _to_float_or_none(row.get("効果係数") or row.get("effect_weight"))

            settings[category] = {
                "importance": importance,
                "effect_weight": effect_weight
            }

    _CATEGORY_SETTINGS_CACHE = settings
    return settings


def get_category_importance(category: str) -> float:
    """カテゴリ重要度を取得（CSV設定 > デフォルト辞書 > 60）"""
    settings = _load_category_settings()
    if category in settings and settings[category].get("importance") is not None:
        return settings[category]["importance"]
    return CATEGORY_IMPORTANCE.get(category, 60)


def get_category_effect_weight(category: str) -> float:
    """カテゴリ効果係数を取得（CSV設定 > デフォルト辞書 > 1.0）"""
    settings = _load_category_settings()
    if category in settings and settings[category].get("effect_weight") is not None:
        return settings[category]["effect_weight"]
    return CATEGORY_EFFECT_WEIGHT.get(category, 1.0)

def _extract_probability_percent(text: str) -> Optional[float]:
    """テキストから発動確率(%)を抽出"""
    normalized = text.replace('％', '%')
    bracket_match = re.search(r'(\d+)\[(\d+)\]%の確率', normalized)
    if bracket_match:
        return float(max(int(bracket_match.group(1)), int(bracket_match.group(2))))

    match = re.search(r'(\d+(?:\.\d+)?)%の確率', normalized)
    if match:
        return float(match.group(1))
    return None


def extract_condition_text(ability_text: str) -> str:
    """アビリティ文から発動条件テキストを抽出（運用ルール簡易版）"""
    text = (ability_text or "").replace('％', '%').replace('\n', '').replace('\r', '').strip()
    if not text:
        return ""

    # ルール:
    # - アビリティなし(空文字)のみ空欄
    # - 「敵の人数×」を含む場合は敵依存
    # - それ以外は常時
    if "敵の人数×" in text:
        return "敵依存"

    return "常時"


# 発動条件の評価倍率
def evaluate_condition(ability_text: str) -> float:
    """
    発動条件倍率を評価（ユーザー指定ルール）
    """
    text = (ability_text or "").replace('％', '%').replace('\n', '').replace('\r', '')

    # 「状態異常を除く全ダメージ増加/カット」は状態異常時条件ではなく常時効果として扱う
    if (
        ("状態異常を除く" in text or "状態異常以外" in text)
        and ("ダメージ増加" in text or "ダメージカット" in text)
    ):
        # HP/人数などの明示条件がない場合のみ常時扱い
        if not any(x in text for x in ["時", "とき", "以上", "以下", "人数", "生存", "不在", "特性", "通常攻撃", "攻撃時", "被ダメージ"]):
            return 1.0

    # 状態異常時（最優先）
    # 自身/自分が状態異常時: 0.5
    if re.search(r'(自身|自分).*(状態異常時|状態異常)', text):
        return 0.5
    # 敵/相手が状態異常時: 1.0
    if re.search(r'(敵|相手).*(状態異常時|状態異常)', text):
        return 1.0
    # 主語省略の状態異常時は自身扱い
    if '状態異常時' in text:
        return 0.5

    # 常時発動/開始時/ドンパチ・タイマン時
    # 「状態異常時」のような文字列内の「常時」誤検知を避ける
    if (
        "常時発動" in text
        or text.strip().startswith("常時")
        or "バトル開始" in text
        or "ドンパチ・タイマン" in text
    ):
        return 1.0

    # クエストクリア時
    if "クエストクリア" in text:
        return 1.0

    # HP%以上
    hp_above_match = re.search(r'(?:HP|残HP|残りHP|体力).*?(\d+)%?以上', text)
    if hp_above_match:
        hp_threshold = int(hp_above_match.group(1))
        if hp_threshold < 50:
            return 1.0
        if hp_threshold == 50:
            return 0.95
        return 0.9

    # 特性保有者2or3人以上
    holder_count_match = re.search(r'(\d+)(?:人|名|体)以上', text)
    if "特性" in text and holder_count_match and int(holder_count_match.group(1)) in (2, 3):
        main_traits = ["組長", "東条会", "東城会", "街の住人", "水商売"]
        if any(trait in text for trait in main_traits) and "味方" in text:
            return 0.95
        return 0.7

    # 人数×条件（敵/味方、生存/不在）
    if re.search(r'(敵|味方)(生存人数|生存数|不在人数|不在数|人数)×', text):
        return 1.0

    # 敵生存者**人以上
    if re.search(r'敵(生存|の生存)(者|人数|数).*(?:人|名|体)以上', text):
        return 0.8

    # 味方生存**人以上
    if re.search(r'味方(生存|の生存)(者|人数|数).*(?:人|名|体)以上', text):
        return 1.0

    # ヒートゲージ条件（条件文のみを対象）
    # 例: ヒートゲージが50%以上のとき / 残ヒートゲージ○○以下
    # ※「ヒートゲージ上昇量15%上昇」のような効果文は条件ではない
    if re.search(r'(?:残)?ヒートゲージ.*(?:以上|以下|のとき|時)', text) or re.search(r'ヒートゲージが', text):
        return 0.5

    # HP%以下
    hp_below_match = re.search(r'(?:HP|残HP|残りHP|体力).*?(\d+)%?以下', text)
    if hp_below_match:
        hp_threshold = int(hp_below_match.group(1))
        if hp_threshold < 50:
            return 0.5
        if hp_threshold == 50:
            return 0.55
        return 0.6

    # 攻撃時
    if "攻撃時" in text and "通常攻撃" not in text:
        return 1.0

    # 通常攻撃時
    if "通常攻撃" in text:
        probability = _extract_probability_percent(text)
        if probability and probability > 0:
            return 1 - 1 / probability
        return 0.9

    # 明確な条件キーワードがない場合は常時扱い
    if not any(x in text for x in ["時", "とき", "以上", "以下", "人数", "生存", "不在", "確率"]):
        return 1.0

    # 既定値
    return 0.75


def _extract_seconds(text: str) -> Optional[float]:
    """テキストから秒数を抽出（例: 4秒間, 3.0秒間）"""
    sec_match = re.search(r'(\d+(?:\.\d+)?)秒間', text)
    if sec_match:
        return float(sec_match.group(1))
    return None


def _extract_damage_number(text: str) -> Optional[float]:
    """テキストからダメージ値を抽出（例: 16000ダメージ）"""
    dmg_match = re.search(r'(\d+(?:\.\d+)?)ダメージ', text)
    if dmg_match:
        return float(dmg_match.group(1))
    return None


def _extract_percent_number(text: str) -> Optional[float]:
    """テキストから%値を抽出（例: 8%）"""
    pct_match = re.search(r'(\d+(?:\.\d+)?)%', text.replace('％', '%'))
    if pct_match:
        return float(pct_match.group(1))
    return None


def _extract_status_abnormal_effect_value(text: str) -> Optional[float]:
    """
    状態異常付与カテゴリの例外ロジック
    - 魅了/封印/混乱/麻痺/回復不可/失神: base + 5*s
    - 出血: 90 + %
    - 打撲: 80 + ダメージ/1000
    - 骨折: 50 + ダメージ/1000 + 2*s
    - 拘束: 100
    """
    duration = _extract_seconds(text) or 0.0

    if "拘束" in text:
        return 100.0

    sec_based_bases = {
        "魅了": 80.0,
        "封印": 70.0,
        "混乱": 70.0,
        "麻痺": 75.0,
        "回復不可": 65.0,
        "失神": 90.0,
    }
    for keyword, base in sec_based_bases.items():
        if keyword in text:
            return base + 5.0 * duration

    if "出血" in text:
        percent = _extract_percent_number(text) or 0.0
        return 90.0 + percent

    if "打撲" in text:
        damage = _extract_damage_number(text) or 0.0
        return 80.0 + damage / 1000.0

    if "骨折" in text:
        damage = _extract_damage_number(text) or 0.0
        return 50.0 + damage / 1000.0 + 2.0 * duration

    return None


def _extract_special_effect_value(text: str) -> Optional[float]:
    """
    特殊効果付与カテゴリの例外ロジック
    - ステータス上昇阻害/クールタイム阻害: 65 + 5*s
    - その他: 100
    """
    duration = _extract_seconds(text) or 0.0
    if "ステータス上昇阻害" in text or "クールタイム阻害" in text:
        return 65.0 + 5.0 * duration
    return 100.0


def calculate_effect_score(
    ability_text: str,
    category: str,
    equipment_type: str,
    equipment_name: Optional[str] = None,
    rarity: Optional[str] = None,
) -> Tuple[float, Optional[float], Optional[float], Optional[float]]:
    """
    効果量スコアを計算
    効果量スコア = 100 * (e - min_e) / (max_e - min_e)
    ※正規化母集団は装備種類×カテゴリ
    """
    effect_value = extract_effect_value(ability_text, category)

    # 例外: 神田のスーツ_SSRは e=25
    if equipment_name == "神田のスーツ" and rarity == "SSR":
        effect_value = 25.0

    if effect_value is None:
        return 0.0, None, None, None

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT アビリティ, アビリティカテゴリ
        FROM mart_equipments_master
                WHERE 装備種類 = ?
                    AND アビリティ IS NOT NULL
          AND アビリティ != ''
          AND アビリティカテゴリ IS NOT NULL
          AND アビリティカテゴリ != ''
        """, (equipment_type,))

    values = []
    for ability, categories in cur.fetchall():
        split_categories = [c.strip() for c in re.split(r'[,，＋]', categories or '') if c.strip()]
        if category not in split_categories:
            continue
        val = extract_effect_value(ability, category)
        if val is not None:
            values.append(val)
    conn.close()

    if not values:
        return 100.0, effect_value, effect_value, effect_value

    max_val = max(values)
    min_val = min(values)

    if max_val == min_val:
        return 100.0, effect_value, min_val, max_val

    score = 100.0 * (effect_value - min_val) / (max_val - min_val)
    score = min(max(score, 0.0), 100.0)
    return score, effect_value, min_val, max_val


def extract_effect_value(ability_text: str, category: str) -> Optional[float]:
    """
    アビリティテキストから効果量を抽出
    
    優先順位:
    1. 括弧内の複数値（2[6]% → 6%）
    2. 人数依存パターン（敵人数×5% → 25%、敵生存数× も対応）
    3. 通常攻撃時の確率パターン：効果値を抽出
    4. 効果部分の%を抽出（条件部分のHP%は除外）
    5. 数値表記
    """
    # テキストを正規化（改行・余分スペースを除去、％→%に統一）
    text = ability_text.replace('\n', '').replace('\r', '').strip()
    text = text.replace('％', '%')
    # 複数スペースをまとめる
    text = re.sub(r'\s+', '', text)
    
    # 例外2: 状態異常付与カテゴリ
    if category == "状態異常付与":
        special_val = _extract_status_abnormal_effect_value(text)
        if special_val is not None:
            return special_val

    # 例外3: 特殊効果付与カテゴリ
    if category == "特殊効果付与":
        special_val = _extract_special_effect_value(text)
        if special_val is not None:
            return special_val

    # 例外4: ダメージ無効化カテゴリ
    if category == "ダメージ無効化":
        # 5%の確率で無効化 -> 80 + 5
        probability = _extract_probability_percent(text)
        if probability is not None:
            return 80.0 + probability
        percent = _extract_percent_number(text)
        if percent is not None:
            return 80.0 + percent
        return 80.0

    # 確率トリガーの有無を判定（例: 20%の確率で / 4[12]%の確率で）
    has_probability_trigger = bool(re.search(r'(?:\d+(?:\.\d+)?|\d+\[\d+\])%の確率で', text))
    post_trigger_text = text
    if has_probability_trigger:
        # 「...%の確率で」より後ろだけを効果抽出対象にする
        split_match = re.search(r'(?:\d+(?:\.\d+)?|\d+\[\d+\])%の確率で(.*)', text)
        if split_match:
            post_trigger_text = split_match.group(1)

    # 1. 括弧内の複数値（2[6]%）
    # ただし確率トリガーを持つ文では、確率部分を誤抽出しないよう後段テキストのみ対象
    bracket_match = re.search(r'(\d+)\[(\d+)\]%', post_trigger_text)
    if bracket_match:
        base_value = float(bracket_match.group(1))
        bracket_value = float(bracket_match.group(2))
        return max(base_value, bracket_value)
    
    # 2. 人数依存パターンを優先処理
    # 敵生存人数×、敵生存数×、敵不在人数×、敵不在数× 等の表記ゆれに対応
    if "人数×" in text or "生存数×" in text or "不在数×" in text:
        multiplier_match = re.search(r'(?:人数|生存数|不在数)×(\d+(?:\.\d+)?)%', text)
        if multiplier_match:
            rate = float(multiplier_match.group(1))
            # キーワードで人数を判定
            if "敵生存人数×" in text or "敵生存数×" in text or "敵生存者×" in text:
                return rate * 5  # 敵生存 5人
            elif "敵不在人数×" in text or "敵不在数×" in text:
                return rate * 4  # 敵不在 4人（5人-1人）
            elif "味方生存人数×" in text or "味方生存数×" in text or "味方生存者×" in text:
                return rate * 5  # 味方生存 5人
            elif "味方不在人数×" in text or "味方不在数×" in text:
                return rate * 4  # 味方不在 4人
            # デフォルトは敵5人と判定
            return rate * 5
        
        # 敵生存数×の後ろから最初の%を抽出（敵生存数××○○を..%上昇パターン）
        if "敵生存数×" in text or "敵生存人数×" in text:
            effect_match = re.search(r'(?:敵生存数|敵生存人数|敵生存者)×.*?(\d+(?:\.\d+)?)%', text)
            if effect_match:
                rate = float(effect_match.group(1))
                return rate * 5  # 敵 5人
        
        if "味方生存数×" in text or "味方生存人数×" in text:
            effect_match = re.search(r'(?:味方生存数|味方生存人数|味方生存者)×.*?(\d+(?:\.\d+)?)%', text)
            if effect_match:
                rate = float(effect_match.group(1))
                return rate * 5  # 味方 5人
    
    # 敵人数× または 味方人数× （明示されない人数依存）
    if "敵人数×" in text:
        multiplier_match = re.search(r'敵人数×(\d+(?:\.\d+)?)%', text)
        if multiplier_match:
            rate = float(multiplier_match.group(1))
            return rate * 5  # 敵 5人
        # 敵人数×と%の間に他の文字がある場合
        effect_match = re.search(r'敵人数×.*?(\d+(?:\.\d+)?)%', text)
        if effect_match:
            rate = float(effect_match.group(1))
            return rate * 5
    
    elif "味方人数×" in text:
        multiplier_match = re.search(r'味方人数×(\d+(?:\.\d+)?)%', text)
        if multiplier_match:
            rate = float(multiplier_match.group(1))
            return rate * 5  # 味方 5人
        # 味方人数×と%の間に他の文字がある場合
        effect_match = re.search(r'味方人数×.*?(\d+(?:\.\d+)?)%', text)
        if effect_match:
            rate = float(effect_match.group(1))
            return rate * 5
    
    # 3. 確率トリガー系の特殊処理
    # 「○%の確率で△%上昇(減少/進行/回復)」なら△を効果値にする
    if has_probability_trigger:
        # 状態異常系キーワード（カテゴリ以外でも保険的に除外）
        if any(x in post_trigger_text for x in ["状態異常", "魅了", "出血", "毒", "機能停止", "封印", "打撲", "混乱", "泥酔", "回復不可"]):
            return None

        # 効果%（上昇/減少/強化/加速/進行/回復）を抽出
        effect_match = re.search(r'-?(\d+(?:\.\d+)?)%(?:上昇|減少|強化|加速|進行|回復)', post_trigger_text)
        if effect_match:
            return float(effect_match.group(1))

        # 先に進行/加速があり、文末に%が来るなどを広く拾う
        effect_match_alt = re.search(r'-?(\d+(?:\.\d+)?)%(?=.*(?:上昇|減少|強化|加速|進行|回復))', post_trigger_text)
        if effect_match_alt:
            return float(effect_match_alt.group(1))
    
    # 4. 効果部分の%を抽出（条件部分のHP%は除外）
    # 複数の%がある場合は、条件部分（HP%, 人数条件）を除外してから抽出
    
    # 条件キーワードを一時置換
    text_for_effect = post_trigger_text if has_probability_trigger else text
    # 条件部分を削除
    text_for_effect = re.sub(r'(?:残)?HP\d+%(?:以上|以下)', '', text_for_effect)
    text_for_effect = re.sub(r'(?:敵|味方)(?:生存|不在)(?:者|人数|数)?\d*(?:人|名|体)?(?:以上|以下)', '', text_for_effect)
    
    # 効果部分から最初の%を抽出
    effect_match = re.search(r'-?(\d+(?:\.\d+)?)%', text_for_effect)
    if effect_match:
        return float(effect_match.group(1))
    
    # 5. 数値表記（攻撃力200UPなど）
    if category in ["攻撃力上昇", "攻撃力減少", "敵攻撃減少"]:
        num_match = re.search(r'(\d+)(?:UP|上昇|減少)', text, re.IGNORECASE)
        if num_match:
            # 攻撃力は数値/20で%換算
            return float(num_match.group(1)) / 20
    
    if category in ["防御力上昇", "防御力減少", "敵防御減少"]:
        num_match = re.search(r'(\d+)(?:UP|上昇|減少)', text, re.IGNORECASE)
        if num_match:
            # 防御力は数値/20で%換算
            return float(num_match.group(1)) / 20
    
    if category == "体力上昇":
        num_match = re.search(r'(\d+)(?:UP|上昇)', text, re.IGNORECASE)
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


def evaluate_ability(
    ability_text: str,
    category: str,
    equipment_type: str,
    equipment_name: Optional[str] = None,
    rarity: Optional[str] = None,
) -> Dict:
    """
    アビリティの総合評価を計算
    評価点 = (カテゴリ重要度 + 効果量スコア) × 発動倍率 × 0.5
    
    Args:
        ability_text: アビリティテキスト
        category: アビリティカテゴリ (複数カテゴリの場合は区切り文字を許容)
        equipment_type: 装備種類 (武器/防具/装飾)
    """
    if not ability_text or not category or category == "なし" or category == "":
        return {
            "score": 0,
            "importance": 0,
            "condition_rate": 0,
            "condition_text": "",
            "effect_score": 0,
            "effect_value": None,
            "min_effect_value": None,
            "max_effect_value": None,
            "representative_category": "",
            "category_breakdown": [],
            "categories": []
        }
    
    # 複数カテゴリの場合は分割して評価
    categories = [c.strip() for c in re.split(r'[,，＋]', category) if c.strip()]
    
    if not categories:
        return {
            "score": 0,
            "importance": 0,
            "condition_rate": 0,
            "condition_text": "",
            "effect_score": 0,
            "effect_value": None,
            "min_effect_value": None,
            "max_effect_value": None,
            "representative_category": "",
            "category_breakdown": [],
            "categories": []
        }

    condition_rate = evaluate_condition(ability_text)
    category_results = []

    for cat in categories:
        importance = get_category_importance(cat)
        effect_score, effect_value, min_val, max_val = calculate_effect_score(
            ability_text,
            cat,
            equipment_type,
            equipment_name=equipment_name,
            rarity=rarity,
        )
        cat_score = (importance + effect_score) * condition_rate * 0.5
        category_results.append({
            "category": cat,
            "importance": importance,
            "effect_score": effect_score,
            "effect_value": effect_value,
            "min_effect_value": min_val,
            "max_effect_value": max_val,
            "score": cat_score,
        })

    # 複数カテゴリ時は「重要度の最大値」を代表値に採用
    representative = max(category_results, key=lambda r: (r["importance"], r["score"]))

    return {
        "score": round(representative["score"], 2),
        "importance": round(representative["importance"], 2),
        "condition_rate": round(condition_rate, 2),
        "condition_text": extract_condition_text(ability_text),
        "effect_score": round(representative["effect_score"], 2),
        "effect_value": representative["effect_value"],
        "min_effect_value": representative["min_effect_value"],
        "max_effect_value": representative["max_effect_value"],
        "representative_category": representative["category"],
        "categories": categories,
        "category_breakdown": category_results,
        # 互換キー（既存呼び出し側の崩壊回避）
        "rarity": 0,
        "effect_weight": 1.0,
        "effect_rank": round(representative["effect_score"], 2),
    }


def format_ability_evaluation(
    ability_text: str,
    category: str,
    equipment_type: str,
    equipment_name: Optional[str] = None,
    rarity: Optional[str] = None,
) -> str:
    """
    アビリティ評価を読みやすいテキストに整形
    
    Args:
        ability_text: アビリティテキスト
        category: アビリティカテゴリ (複数カテゴリの場合はカンマ区切り)
        equipment_type: 装備種類 (武器/防具/装飾)
    """
    eval_result = evaluate_ability(
        ability_text,
        category,
        equipment_type,
        equipment_name=equipment_name,
        rarity=rarity,
    )
    
    if eval_result["score"] == 0:
        return "アビリティなし"
    
    text = f"### アビリティ評価\n\n"

    if len(eval_result.get("categories", [])) > 1:
        text += f"**カテゴリ**: {', '.join(eval_result['categories'])}\n"
        text += f"**代表カテゴリ**: {eval_result.get('representative_category', '')}（重要度最大値を採用）\n\n"

    text += f"**総合評価点**: {eval_result['score']:.1f}点\n\n"
    text += f"- カテゴリ重要度: {eval_result['importance']}点\n"
    text += f"- 発動条件倍率: {eval_result['condition_rate']:.2f}倍\n"
    text += f"- 効果量スコア: {eval_result['effect_score']:.2f}\n"

    if eval_result['effect_value'] is not None:
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
