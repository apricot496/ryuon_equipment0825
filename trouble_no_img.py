import os
from PIL import Image
import shutil
import pandas as pd
import sqlite3

DB_PATH = "equipment.db"

'''
トラブル対応用画像処理スクリプト
このスクリプトはローカルで実行してください
使い方:
1. no_image_equipment.csvに該当する装備名と画像名を記載
2. 元画像スクショフォルダに元画像を配置
3. このスクリプトを実行
4. trans_base64.pyを実行してDB更新
5. index_drop_db.pyを実行してDBのインデックス整理
'''

# === トリミング＋リサイズ関数 ===
def crop_and_downscale_image(input_path, output_path, crop_x, crop_y, crop_width, crop_height, downscale_factor=0.5):
    with Image.open(input_path) as img:
        cropped = img.crop((
            crop_x,
            crop_y,
            crop_x + crop_width,
            crop_y + crop_height
        ))

        new_width = int(cropped.width * downscale_factor)
        new_height = int(cropped.height * downscale_factor)
        resized = cropped.resize((new_width, new_height), Image.LANCZOS)

        # JPEG保存のためにRGB変換（αチャンネルを削除）
        if resized.mode != 'RGB':
            resized = resized.convert('RGB')

        resized.save(output_path, format='JPEG', optimize=True, quality=85)

# === 入出力パスのリスト作成関数 ===
def generate_input_output_paths(input_dir="元画像スクショ", output_dir="cleansed_img_1"):
    input_path_list = []
    output_path_list = []

    for filename in os.listdir(input_dir):
        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff")):
            input_path = os.path.join(input_dir, filename)

            # 拡張子を強制的に .png に変更
            base_filename = os.path.splitext(filename)[0] + ".png"
            output_path = os.path.join(output_dir, base_filename)

            input_path_list.append(input_path)
            output_path_list.append(output_path)

    return input_path_list, output_path_list

def insert_to_db(equips):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for eq in equips:
        cur.execute("""
            INSERT INTO equipment_img_scraping
            (装備名, レアリティ, 画像名, 体力, 攻撃力, 防御力, 会心率, 回避率, 命中率, アビリティ, 新規フラグ, URL_Number, IMG_URL)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            eq.get("装備名"), eq.get("レアリティ"), eq.get("画像名"),
            eq.get("体力"), eq.get("攻撃力"), eq.get("防御力"),
            eq.get("会心率"), eq.get("回避率"), eq.get("命中率"),
            eq.get("アビリティ"), eq.get("新規フラグ"),
            eq.get("URL_Number"), eq.get("IMG_URL")
        ))
    conn.commit()
    conn.close()

# === 出力フォルダを確保 ===
os.makedirs("cleansed_img_1", exist_ok=True)

# === パス取得と処理実行 ===
input_list, output_list = generate_input_output_paths()

for in_path, out_path in zip(input_list, output_list):
    print(f"Processing: {in_path} → {out_path}")
    crop_and_downscale_image(
        input_path=in_path,
        output_path=out_path,
        crop_x=260,
        crop_y=140,
        crop_width=500-260,
        crop_height=360-140,
        downscale_factor=0.5
    )
# 入力ファイルとディレクトリ
csv_file = "no_image_equipment.csv"
src_dir = "cleansed_img_1"
dst_dir = "static"
os.makedirs(dst_dir, exist_ok=True)

# CSV読み込み
df = pd.read_csv(csv_file)

# 新しいファイル名列を作成
df["画像名"] = df["装備名"] + "_" + df["レアリティ"] + ".png"

# IMG_URL列を作成
df["IMG_URL"] = "https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/main/static/" + df["画像名"]

# 新規フラグ列を追加
df["新規フラグ"] = 1

# ファイルコピーとリネーム
for _, row in df.iterrows():
    old_name = row["IMG_NAME"]
    new_name = row["画像名"]
    src_path = os.path.join(src_dir, old_name)
    dst_path = os.path.join(dst_dir, new_name)
    
    if os.path.exists(src_path):
        shutil.copy(src_path, dst_path)
    else:
        print(f"⚠ ファイルが存在しません: {src_path}")

# dbの追加
# 出力用データフレーム（指定されたカラム順）
out_cols = [
    "装備名", "レアリティ", "画像名", "体力", "攻撃力", "防御力", 
    "会心率", "回避率", "命中率", "アビリティ", 
    "新規フラグ", "URL_Number", "IMG_URL"
]

# DataFrame → list[dict] に変換
equip_list = df[out_cols].to_dict(orient="records")

# DB にインサート
insert_to_db(equip_list)

print("✅ DB への登録が完了しました！")