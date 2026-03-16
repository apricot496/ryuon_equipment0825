"""
データベースのテーブル型を修正するスクリプト
"""
import sqlite3
import sys

DB_FILE = "equipment.db"


def fix_equipment_img_scraping(conn):
    """equipment_img_scrapingテーブルの型を修正"""
    print("=" * 60)
    print("equipment_img_scrapingテーブルの型を修正中...")
    print("=" * 60)
    
    cur = conn.cursor()
    
    # 既存データを取得
    cur.execute("SELECT COUNT(*) FROM equipment_img_scraping")
    count = cur.fetchone()[0]
    print(f"既存データ: {count}件")
    
    # 新しいテーブルを作成
    cur.execute("""
        CREATE TABLE equipment_img_scraping_new (
            装備名 TEXT,
            レアリティ TEXT,
            画像名 TEXT,
            体力 INTEGER,
            攻撃力 INTEGER,
            防御力 INTEGER,
            会心率 REAL,
            回避率 REAL,
            命中率 REAL,
            アビリティ TEXT,
            新規フラグ TEXT,
            URL_Number INTEGER,
            IMG_URL TEXT
        )
    """)
    
    # データを移行（型変換）
    cur.execute("""
        INSERT INTO equipment_img_scraping_new
        SELECT 
            装備名,
            レアリティ,
            画像名,
            CAST(体力 AS INTEGER),
            CAST(攻撃力 AS INTEGER),
            CAST(防御力 AS INTEGER),
            CAST(会心率 AS REAL),
            CAST(回避率 AS REAL),
            CAST(命中率 AS REAL),
            アビリティ,
            新規フラグ,
            CAST(URL_Number AS INTEGER),
            IMG_URL
        FROM equipment_img_scraping
        ORDER BY CAST(URL_Number AS INTEGER) ASC
    """)
    
    # 古いテーブルを削除して新しいテーブルをリネーム
    cur.execute("DROP TABLE equipment_img_scraping")
    cur.execute("ALTER TABLE equipment_img_scraping_new RENAME TO equipment_img_scraping")
    
    print(f"✓ equipment_img_scraping修正完了: {count}件")
    print("  - 体力, 攻撃力, 防御力, URL_Number → INTEGER")
    print("  - 会心率, 回避率, 命中率 → REAL")
    print("  - URL_Number昇順でソート")


def fix_non_check_equipments(conn):
    """non_check_equipmentsテーブルの型を修正（BIGINT → INTEGER）"""
    print("\n" + "=" * 60)
    print("non_check_equipmentsテーブルの型を修正中...")
    print("=" * 60)
    
    cur = conn.cursor()
    
    # 既存データを取得
    cur.execute("SELECT COUNT(*) FROM non_check_equipments")
    count = cur.fetchone()[0]
    print(f"既存データ: {count}件")
    
    # 新しいテーブルを作成
    cur.execute("""
        CREATE TABLE non_check_equipments_new (
            装備名 TEXT,
            装備番号 TEXT,
            レアリティ TEXT,
            体力 INTEGER,
            攻撃力 INTEGER,
            防御力 INTEGER,
            会心率 REAL,
            回避率 REAL,
            命中率 REAL,
            アビリティ TEXT,
            アビリティカテゴリ TEXT,
            装備種類 TEXT
        )
    """)
    
    # データを移行
    cur.execute("""
        INSERT INTO non_check_equipments_new
        SELECT * FROM non_check_equipments
    """)
    
    # 古いテーブルを削除して新しいテーブルをリネーム
    cur.execute("DROP TABLE non_check_equipments")
    cur.execute("ALTER TABLE non_check_equipments_new RENAME TO non_check_equipments")
    
    print(f"✓ non_check_equipments修正完了: {count}件")
    print("  - BIGINT → INTEGER")


def verify_tables(conn):
    """修正後のテーブル型を確認"""
    print("\n" + "=" * 60)
    print("修正後の型を確認中...")
    print("=" * 60)
    
    cur = conn.cursor()
    
    for table in ["equipment_img_scraping", "non_check_equipments"]:
        print(f"\n【{table}】")
        cur.execute(f"PRAGMA table_info({table})")
        for row in cur.fetchall():
            col_id, name, type_, notnull, default, pk = row
            if name in ["体力", "攻撃力", "防御力", "会心率", "回避率", "命中率", "URL_Number"]:
                print(f"  {name}: {type_}")


def main():
    """メイン処理"""
    print("データベース型修正スクリプト")
    print(f"対象DB: {DB_FILE}\n")
    
    try:
        conn = sqlite3.connect(DB_FILE)
        
        # equipment_img_scrapingを修正
        fix_equipment_img_scraping(conn)
        
        # non_check_equipmentsを修正
        fix_non_check_equipments(conn)
        
        # コミット
        conn.commit()
        
        # 確認
        verify_tables(conn)
        
        # VACUUM（データベース最適化）
        print("\n" + "=" * 60)
        print("データベースを最適化中...")
        print("=" * 60)
        conn.execute("VACUUM")
        print("✓ 最適化完了")
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("全ての修正が完了しました")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ エラーが発生しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
