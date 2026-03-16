import sqlite3
import pandas as pd

conn = sqlite3.connect('equipment.db')

# equipment_img_scrapingから全装備取得
scraping_df = pd.read_sql_query('SELECT 装備名, レアリティ FROM equipment_img_scraping', conn)
scraping_keys = set(zip(scraping_df['装備名'], scraping_df['レアリティ']))
print(f'equipment_img_scraping: {len(scraping_keys)}件（重複除外）')

# 9シートから全装備取得
tables = ['ssr武器', 'ssr防具', 'ssr装飾', 'ksr武器', 'ksr防具', 'ksr装飾', 'ur武器', 'ur防具', 'ur装飾']
fix_dfs = []
for table in tables:
    df = pd.read_sql_query(f'SELECT 装備名, レアリティ FROM "{table}"', conn)
    fix_dfs.append(df)

fix_df = pd.concat(fix_dfs, ignore_index=True)
fix_keys = set(zip(fix_df['装備名'], fix_df['レアリティ']))
print(f'9シート合計: {len(fix_keys)}件（重複除外）')

# 差分
diff_keys = scraping_keys - fix_keys
print(f'差分: {len(diff_keys)}件')

# non_check_equipments
non_check_df = pd.read_sql_query('SELECT 装備名, レアリティ FROM non_check_equipments', conn)
non_check_keys = set(zip(non_check_df['装備名'], non_check_df['レアリティ']))
print(f'non_check_equipments: {len(non_check_keys)}件（重複除外）')

# 一致確認
if diff_keys == non_check_keys:
    print('\n✅ 差分とnon_check_equipmentsが一致しています')
else:
    print('\n❌ 差分とnon_check_equipmentsが不一致です')
    print(f'差分にあってnon_checkにない: {diff_keys - non_check_keys}')
    print(f'non_checkにあって差分にない: {non_check_keys - diff_keys}')
