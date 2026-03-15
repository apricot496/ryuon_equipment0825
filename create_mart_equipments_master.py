import sqlite3
import pandas as pd

DB_FILE = "equipment.db"
def create_mart_equipments_master():
    """
    各レアリティ×装備種類のテーブルとnon_check_equipmentsを統合して
    mart_equipments_masterテーブルを作成する
    """
    conn = sqlite3.connect(DB_FILE)
    
    equipments_list = ["武器", "防具", "装飾"]
    rarity_order = ['ur', 'ksr', 'ssr']
    
    all_df_list = []
    
    # 各レアリティ×装備種類のテーブルを読み込み
    for equipments in equipments_list:
        for rarity in rarity_order:
            table_name = f"{rarity}{equipments}"
            print(f"Reading {table_name}...")
            
            # テーブルからデータを読み込み
            df = pd.read_sql(f"SELECT * FROM '{table_name}'", conn)
            
            # 装備種類カラムを追加
            df['装備種類'] = equipments
            
            all_df_list.append(df)
    
    # non_check_equipmentsを読み込み（既に装備種類カラムがある）
    print("Reading non_check_equipments...")
    df_non_check = pd.read_sql("SELECT * FROM non_check_equipments", conn)
    all_df_list.append(df_non_check)
    
    # 全てを縦結合
    print("Concatenating all dataframes...")
    master_df = pd.concat(all_df_list, ignore_index=True)
    
    # mart_equipments_masterテーブルを作成（既存のテーブルは削除）
    print("Creating mart_equipments_master table...")
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS mart_equipments_master")
    
    # データを保存
    master_df.to_sql('mart_equipments_master', conn, if_exists='replace', index=False)
    
    # 結果を確認
    cur.execute("SELECT COUNT(*) FROM mart_equipments_master")
    count = cur.fetchone()[0]
    print(f"✓ mart_equipments_masterテーブルに{count}件のレコードを作成しました")
    
    # 装備種類ごとの件数を確認
    cur.execute("SELECT 装備種類, COUNT(*) FROM mart_equipments_master GROUP BY 装備種類")
    for row in cur.fetchall():
        print(f"  - {row[0]}: {row[1]}件")
    
    conn.close()
    print("\nmart_equipments_master作成完了!")

if __name__ == "__main__":
    create_mart_equipments_master()
