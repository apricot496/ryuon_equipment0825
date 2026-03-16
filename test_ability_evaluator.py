#!/usr/bin/env python3
"""ability_evaluator.pyの動作テスト"""

import sqlite3
from ability_evaluator import format_ability_evaluation, evaluate_ability

def test_basic():
    """基本的な機能テスト"""
    print("=== 基本機能テスト ===")
    
    # テストケース1: 単一カテゴリ
    result = evaluate_ability("BSCT加速5%", "BSCT加速", "防具")
    print(f"テスト1 (単一カテゴリ): score={result['score']}, categories={result['categories']}")
    
    # テストケース2: 複数カテゴリ
    result = evaluate_ability("BSCT加速5%, ヒートゲージ上昇10%", "BSCT加速，ヒートゲージ上昇", "防具")
    print(f"テスト2 (複数カテゴリ): score={result['score']}, categories={result['categories']}")
    
    # テストケース3: 括弧内数値
    result = evaluate_ability("攻撃力2[6]%上昇", "攻撃力上昇", "武器")
    print(f"テスト3 (括弧内数値): score={result['score']}, effect_value={result['effect_value']}")
    
    # テストケース4: マイナス記号
    result = evaluate_ability("防御力-10%", "防御力低下", "武器")
    print(f"テスト4 (マイナス記号): score={result['score']}, effect_value={result['effect_value']}")
    
    print()

def test_database():
    """データベースから実際のデータでテスト"""
    print("=== データベース実データテスト ===")
    
    conn = sqlite3.connect('equipment.db')
    cursor = conn.cursor()
    
    # 複数カテゴリの装備を取得
    cursor.execute('''
        SELECT 装備名, アビリティ, アビリティカテゴリ, 装備種類, レアリティ 
        FROM mart_equipments_master 
        WHERE (アビリティカテゴリ LIKE '%,%' OR アビリティカテゴリ LIKE '%，%')
        AND アビリティ IS NOT NULL
        LIMIT 1
    ''')
    result = cursor.fetchone()
    
    if result:
        name, ability, category, eq_type, rarity = result
        print(f'装備名: {name} ({rarity})')
        print(f'装備種類: {eq_type}')
        print(f'アビリティ: {ability}')
        print(f'カテゴリ: {category}')
        print()
        print(format_ability_evaluation(ability, category, eq_type))
    else:
        print("複数カテゴリの装備が見つかりませんでした")
    
    print("\n" + "="*50 + "\n")
    
    # 通常の装備でもテスト
    cursor.execute('''
        SELECT 装備名, アビリティ, アビリティカテゴリ, 装備種類, レアリティ 
        FROM mart_equipments_master 
        WHERE アビリティカテゴリ != 'なし' 
        AND アビリティカテゴリ IS NOT NULL
        AND アビリティ IS NOT NULL
        AND (アビリティカテゴリ NOT LIKE '%,%' AND アビリティカテゴリ NOT LIKE '%，%')
        LIMIT 1
    ''')
    result = cursor.fetchone()
    
    if result:
        name, ability, category, eq_type, rarity = result
        print(f'装備名: {name} ({rarity})')
        print(f'装備種類: {eq_type}')
        print(f'アビリティ: {ability}')
        print(f'カテゴリ: {category}')
        print()
        print(format_ability_evaluation(ability, category, eq_type))
    else:
        print("通常の装備が見つかりませんでした")
    
    conn.close()

if __name__ == "__main__":
    try:
        test_basic()
        print()
        test_database()
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
