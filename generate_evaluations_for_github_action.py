"""
GitHub Action用装備評価生成スクリプト
直近10件（URL_Numberが上位10件）の装備評価を生成
既存の評価ファイルはスキップ
"""
import sqlite3
import sys
import subprocess
from pathlib import Path
from generate_equipment_evaluation import generate_evaluation_html, save_evaluation_file, generate_preview_image

DB_FILE = "equipment.db"
OUTPUT_DIR = Path("evaluation_sheets")
IMAGE_DIR = OUTPUT_DIR / "images"


def get_latest_equipments(conn: sqlite3.Connection, limit: int = 10):
    """
    URL_Numberが最も大きい装備をlimit件取得
    
    equipment_img_scrapingをベースに取得するため、
    スプレッドシート未登録の装備（イベント報酬装備など）も含まれる
    """
    query = """
    SELECT DISTINCT 
        s.装備名,
        s.レアリティ,
        s.URL_Number
    FROM equipment_img_scraping s
    WHERE s.URL_Number IS NOT NULL AND s.URL_Number != 0
    ORDER BY CAST(s.URL_Number AS INTEGER) DESC
    LIMIT ?
    """
    cur = conn.cursor()
    cur.execute(query, (limit,))
    return cur.fetchall()


def check_file_exists(equipment_name: str, rarity: str, url_number: int) -> bool:
    """既存の評価ファイルが存在するかチェック（日付部分を無視）"""
    safe_name = equipment_name.replace("/", "_").replace("\\", "_")
    # パターン: *_{URL_Number}_{装備名}_{レアリティ}_評価.html
    pattern = f"*_{url_number}_{safe_name}_{rarity}_評価.html"
    
    # evaluation_sheets/配下で該当ファイルを検索
    matches = list(OUTPUT_DIR.glob(pattern))
    
    if matches:
        print(f"⏭ スキップ（既存）: {equipment_name} ({rarity}) - URL_Number: {url_number}")
        return True
    return False


def main():
    """メイン処理"""
    print("=" * 60)
    print("GitHub Action用装備評価生成")
    print("=" * 60)

    # スコアDBを先に生成
    print("\n[1/2] equipments_mart_score.db を生成します...")
    try:
        subprocess.run(
            [sys.executable, "generate_equipments_mart_score_db.py"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"✗ スコアDB生成エラー: {e}")
        sys.exit(1)

    print("\n[2/2] 装備評価ファイルを生成します...")
    
    conn = sqlite3.connect(DB_FILE)
    
    # 直近10件を取得
    latest_equipments = get_latest_equipments(conn, limit=10)
    
    if not latest_equipments:
        print("処理対象の装備が見つかりません")
        return
    
    print(f"\n直近10件の装備を取得しました:")
    for i, (name, rarity, url_num) in enumerate(latest_equipments, 1):
        print(f"{i}. {name} ({rarity}) - URL_Number: {url_num}")
    
    print("\n" + "=" * 60)
    print("評価ファイル生成開始")
    print("=" * 60 + "\n")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    image_count = 0
    
    for equipment_name, rarity, url_number in latest_equipments:
        try:
            # 既存ファイルチェック
            if check_file_exists(equipment_name, rarity, url_number):
                skip_count += 1
                continue
            
            # HTML生成
            content, url_num = generate_evaluation_html(conn, equipment_name, rarity)
            if content:
                html_filepath = save_evaluation_file(equipment_name, rarity, content, url_num)
                success_count += 1
                
                # 画像生成
                try:
                    generate_preview_image(html_filepath)
                    image_count += 1
                except Exception as e:
                    print(f"⚠ 画像生成エラー ({equipment_name}): {e}")
            else:
                print(f"✗ データ取得失敗: {equipment_name} ({rarity})")
                error_count += 1
                
        except Exception as e:
            print(f"✗ エラー: {equipment_name} ({rarity}) - {e}")
            error_count += 1
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("処理完了")
    print("=" * 60)
    print(f"成功: {success_count}件")
    print(f"スキップ: {skip_count}件")
    print(f"画像生成: {image_count}件")
    print(f"エラー: {error_count}件")
    print(f"合計処理対象: {len(latest_equipments)}件")
    
    # エラーがあれば異常終了
    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
