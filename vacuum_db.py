"""
データベースのVACUUM処理
全てのDB更新が完了した後に実行して、データベースを最適化する
"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "equipment.db"


def vacuum_database():
    """
    データベースをVACUUMして最適化する
    - 未使用の領域を解放
    - ファイルサイズを削減
    - インデックスを再構築
    """
    print("Database VACUUM開始...")
    conn = sqlite3.connect(str(DB_PATH))
    try:
        # VACUUMはトランザクション外で実行する必要がある
        conn.isolation_level = None
        conn.execute("VACUUM")
        print("✓ Database VACUUMが完了しました")
    finally:
        conn.close()


if __name__ == "__main__":
    vacuum_database()
