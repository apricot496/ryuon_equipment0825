import os
import sqlite3
import shutil
from pathlib import Path
import random

import numpy as np
import pandas as pd
from PIL import Image

# =========================
# 設定
# =========================
DB_PATH = Path("equipment.db")

STATIC_DIR = Path("static")
MONTAGE_SRC_DIR = Path("モンタージュ作成用")  # モンタージュ用に集める画像置き場
TEST_DIR = Path("テスト用")                 # テスト用画像置き場
MONTAGE_OUT_DIR = Path("montage_imgs")      # 生成したモンタージュの出力先

TABLES = [
    "ur武器", "ur防具", "ur装飾",
    "ksr武器", "ksr防具", "ksr装飾",
    "ssr武器", "ssr防具", "ssr装飾",
]

# テストフラグ=1 を何割にするか（あなたの「6:4ぐらい」に合わせて 0.6）
P_MONTAGE = 0.6

# 乱数シード（再現性が必要なら固定、不要なら None に）
RANDOM_SEED = 42

# 画像拡張子候補（static/{装備名}_{レアリティ}.* を探す）
IMG_EXTS = [".png", ".jpg", ".jpeg", ".webp"]

# トリミング位置の比率（左から(45/140)*width、上から(40/140)*height）
LEFT_RATIO = 45 / 140
TOP_RATIO = 40 / 140
CROP_W, CROP_H = 45, 40  # トリミング領域サイズ（その後 45x40 にリサイズ＝同サイズ）


# =========================
# ユーティリティ
# =========================
def find_image_path(static_dir: Path, equip_name: str, rarity: str) -> Path | None:
    """
    static/{装備名}_{レアリティ}.* を探索して最初に見つかったものを返す
    """
    stem = f"{equip_name}_{rarity}"
    # まずは拡張子候補で探す（高速）
    for ext in IMG_EXTS:
        p = static_dir / f"{stem}{ext}"
        if p.exists():
            return p
    # 念のため glob（拡張子が変則な場合）
    hits = list(static_dir.glob(f"{stem}.*"))
    return hits[0] if hits else None


def safe_copy(src: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    shutil.copy2(src, dst)


def crop_resize_icon(img: Image.Image) -> Image.Image:
    """
    画像から、指定比率の左上オフセット位置を起点に 45x40 を切り出し、45x40にリサイズして返す
    """
    w, h = img.size
    left = int(LEFT_RATIO * w)
    top = int(TOP_RATIO * h)

    # 範囲外にならないよう調整
    right = min(left + CROP_W, w)
    bottom = min(top + CROP_H, h)
    left = max(0, right - CROP_W)
    top = max(0, bottom - CROP_H)

    cropped = img.crop((left, top, left + CROP_W, top + CROP_H))
    # 念のため最終サイズを保証
    cropped = cropped.resize((CROP_W, CROP_H), resample=Image.Resampling.LANCZOS)
    return cropped


def make_average_montage(input_dir: Path, output_path: Path) -> int:
    """
    input_dir 内の全画像を
    - crop_resize_icon で 45x40 に揃える
    - 平均化して 1枚にする
    出力して、使った画像枚数を返す
    """
    paths = []
    for ext in IMG_EXTS:
        paths.extend(input_dir.glob(f"*{ext}"))
    # 拡張子不明のものも拾いたい場合
    if not paths:
        # 画像として開けるものだけ拾う（雑に全ファイル）
        paths = [p for p in input_dir.glob("*") if p.is_file()]

    imgs = []
    for p in paths:
        try:
            with Image.open(p) as im:
                im = im.convert("RGBA")
                im = crop_resize_icon(im)
                imgs.append(np.asarray(im, dtype=np.float32))
        except Exception:
            # 壊れ画像などはスキップ
            continue

    if not imgs:
        return 0

    avg = np.mean(np.stack(imgs, axis=0), axis=0)
    avg = np.clip(avg, 0, 255).astype(np.uint8)
    out_img = Image.fromarray(avg, mode="RGBA")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_img.save(output_path)
    return len(imgs)


# =========================
# メイン処理
# =========================
def main():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)
        np.random.seed(RANDOM_SEED)

    if not DB_PATH.exists():
        raise FileNotFoundError(f"DBが見つかりません: {DB_PATH}")

    if not STATIC_DIR.exists():
        raise FileNotFoundError(f"static/ が見つかりません: {STATIC_DIR}")

    # 1) DBから各テーブルを読み込み、DataFrameを作る
    dfs: dict[str, pd.DataFrame] = {}
    with sqlite3.connect(DB_PATH) as con:
        for tbl in TABLES:
            df = pd.read_sql_query(f'SELECT 装備名, レアリティ FROM "{tbl}"', con)
            # img_path（拡張子なしの想定パス文字列も保持）
            df["img_stem"] = df["装備名"].astype(str) + "_" + df["レアリティ"].astype(str)
            df["img_path"] = df["img_stem"].apply(lambda s: str(STATIC_DIR / s))  # 指示どおり拡張子なし
            # テストフラグ（1:0 が 6:4 くらい）
            df["テストフラグ"] = (np.random.rand(len(df)) < P_MONTAGE).astype(int)
            dfs[tbl] = df

    # 2) static/ から振り分けてコピー（テストフラグ1 -> モンタージュ作成用/..., 0 -> テスト用/...）
    missing = []
    copied_counts = {tbl: {"montage": 0, "test": 0} for tbl in TABLES}

    for tbl, df in dfs.items():
        for _, row in df.iterrows():
            equip_name = str(row["装備名"])
            rarity = str(row["レアリティ"])
            flag = int(row["テストフラグ"])

            src = find_image_path(STATIC_DIR, equip_name, rarity)
            if src is None:
                missing.append((tbl, equip_name, rarity))
                continue

            if flag == 1:
                safe_copy(src, MONTAGE_SRC_DIR / tbl)
                copied_counts[tbl]["montage"] += 1
            else:
                safe_copy(src, TEST_DIR / tbl)
                copied_counts[tbl]["test"] += 1

    # 3) モンタージュ作成用/{table}/ の全画像から平均モンタージュを作る → montage_imgs/ に保存
    montage_used = {}
    for tbl in TABLES:
        in_dir = MONTAGE_SRC_DIR / tbl
        out_path = MONTAGE_OUT_DIR / f"montage_{tbl}.png"
        if not in_dir.exists():
            montage_used[tbl] = 0
            continue
        used = make_average_montage(in_dir, out_path)
        montage_used[tbl] = used

    # 4) 結果ログ
    print("=== コピー結果 ===")
    for tbl in TABLES:
        print(f"{tbl}: montage={copied_counts[tbl]['montage']}, test={copied_counts[tbl]['test']}")

    if missing:
        print("\n=== 見つからなかった画像（static に存在しない） ===")
        # 多すぎる場合に備えて先頭だけ
        for x in missing[:30]:
            print(x)
        if len(missing) > 30:
            print(f"... and {len(missing) - 30} more")

    print("\n=== モンタージュ作成結果（使用枚数） ===")
    for tbl, used in montage_used.items():
        print(f"{tbl}: used={used} -> {MONTAGE_OUT_DIR / f'montage_{tbl}.png'}")


if __name__ == "__main__":
    main()
