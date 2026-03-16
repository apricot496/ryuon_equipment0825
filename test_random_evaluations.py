#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
from generate_equipment_evaluation import generate_single_evaluation

# テスト対象の装備リスト
test_equipments = [
    ('龍の瞳・極', 'KSR'),
    ('ロウの機密情報', 'KSR'),
    ('日侠連の代紋', 'SSR'),
    ('風間の二丁拳銃', 'SSR'),
    ('冴島の囚人服・防', 'SSR'),
    ('血濡れたノミ', 'SSR'),
    ('ユリのマフラー', 'KSR'),
    ('冴島組代紋', 'SSR'),
    ('龍司のロングコート', 'SSR'),
    ('魚のポシェット', 'KSR')
]

print('評価ファイル生成開始...\n')

success_count = 0
error_count = 0

for name, rarity in test_equipments:
    try:
        print(f'処理中: {name} ({rarity})', end=' ... ')
        generate_single_evaluation(name, rarity, generate_image=True)
        success_count += 1
        print('✓')
    except Exception as e:
        error_count += 1
        print(f'✗ エラー: {e}')

print(f'\n完了: 成功 {success_count}件, エラー {error_count}件')
