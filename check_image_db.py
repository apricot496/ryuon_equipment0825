#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3

conn = sqlite3.connect('equipment.db')
cur = conn.cursor()

print("=== ゴロ美の勝負服 ===")
cur.execute('SELECT 装備名, レアリティ, 画像名 FROM mart_equipments_master WHERE 装備名 = ? AND レアリティ = ?', ('ゴロ美の勝負服', 'UR'))
row = cur.fetchone()
if row:
    print(f'mart_equipments_master: 画像名={row[2]}')
else:
    print('見つかりません')

cur.execute('SELECT IMG_URL FROM equipment_img_scraping WHERE 装備名 = ? AND レアリティ = ?', ('ゴロ美の勝負服', 'UR'))
row = cur.fetchone()
if row:
    print(f'equipment_img_scraping: IMG_URL={row[0]}')
else:
    print('IMG_URLなし')

print("\n=== 真島の法被 ===")
cur.execute('SELECT 装備名, レアリティ, 画像名 FROM mart_equipments_master WHERE 装備名 = ? AND レアリティ = ?', ('真島の法被', 'KSR'))
row = cur.fetchone()
if row:
    print(f'mart_equipments_master: 画像名={row[2]}')
else:
    print('見つかりません')

cur.execute('SELECT IMG_URL FROM equipment_img_scraping WHERE 装備名 = ? AND レアリティ = ?', ('真島の法被', 'KSR'))
row = cur.fetchone()
if row:
    print(f'equipment_img_scraping: IMG_URL={row[0]}')
else:
    print('IMG_URLなし')

conn.close()
