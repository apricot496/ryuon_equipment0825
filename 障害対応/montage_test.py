# 障害対応/montage_test.py
# マーク（左上）だけで「種類（武器/防具/装飾）」を判定する学習なしテスト
# - 参照: モンタージュ作成用/{ur|ssr|ksr}{武器|防具|装飾}/***.png
# - テスト: モンタージュ判定テスト用/{ur|ssr|ksr}{武器|防具|装飾}/***.png
# - 出力: kind_marker_knn.csv（repoルート）

from pathlib import Path
import unicodedata
from collections import defaultdict

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter, ImageOps

# ========= パス（相対ズレ対策：スクリプト位置基準） =========
BASE_DIR = Path(__file__).resolve().parents[1]  # 障害対応/ の1つ上 = repoルート想定
REF_ROOT  = BASE_DIR / "モンタージュ作成用"
TEST_ROOT = BASE_DIR / "モンタージュ判定テスト用"
OUT_CSV   = BASE_DIR / "kind_marker_knn.csv"

# ========= ラベル =========
RARITIES = ["ur", "ssr", "ksr"]
KINDS = ["武器", "防具", "装飾"]

# ========= ROI（左上マーク領域） =========
# まずは広め（枠は後段で消す）
ROI_X0, ROI_Y0 = 0.00, 0.00
ROI_X1, ROI_Y1 = 0.38, 0.38
ROI_BY_RARITY = {
    "ssr": (0.00, 0.00, 0.32, 0.25),  # ★SSRは背景が強いので小さく（左上金具＋マーク中心）
    "ur":  (0.00, 0.00, 0.38, 0.38),
    "ksr": (0.00, 0.00, 0.38, 0.38),
}

# ========= 前処理パラメータ =========
EDGE_THR = 35                # エッジ画像の二値化しきい値
BORDER_MARGIN = 5            # 枠ノイズを消す外周マージン(px)
BORDER_MARGIN_SSR = 8        # SSRだけ枠が強いことが多いので少し強め

LINE_RATIO = 0.70            # 行/列がこの割合以上"1"なら枠直線扱いで消す

# ========= kNN投票 =========
TOPK = 9                     # 7〜15くらいで調整
THRESH_RATIO = 1.30          # 最良距離*d0 の 1.3倍以内だけ投票（遠い候補を捨てて票割れ防止）

# ========= 高速Hamming用 =========
_BITCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def parse_rarity(s: str) -> str | None:
    t = unicodedata.normalize("NFKC", s).lower()
    t = t.replace("_", "").replace(" ", "").replace("　", "")
    for r in RARITIES:
        if r in t:
            return r
    return None


def parse_kind(s: str) -> str | None:
    t = unicodedata.normalize("NFKC", s)
    if "武器" in t:
        return "武器"
    if "防具" in t:
        return "防具"
    if "装飾" in t:
        return "装飾"
    return None


def hamming_bytes(a: np.ndarray, b: np.ndarray) -> int:
    return int(_BITCOUNT[np.bitwise_xor(a, b)].sum())


def marker_binary(path: Path, rarity: str | None = None) -> np.ndarray:
    """
    画像 -> 左上ROI(レア別) -> オートコントラスト -> エッジ -> 二値化 -> 枠直線除去 -> packbits
    """
    with Image.open(path) as im:
        im = im.convert("RGBA")
        w, h = im.size

        x0r, y0r, x1r, y1r = ROI_BY_RARITY.get(rarity, (0.0, 0.0, 0.38, 0.38))
        x0 = int(x0r * w); y0 = int(y0r * h)
        x1 = max(x0 + 1, int(x1r * w))
        y1 = max(y0 + 1, int(y1r * h))

        roi = im.crop((x0, y0, x1, y1)).convert("RGB")

    roi = roi.resize((64, 64), Image.Resampling.LANCZOS)

    roi = ImageOps.autocontrast(roi)
    edge = roi.convert("L").filter(ImageFilter.FIND_EDGES)
    a = np.asarray(edge, dtype=np.uint8).copy()  # read-only回避

    # ★SSRはROIが小さくなるので、marginは強くしすぎない（消しすぎ防止）
    m = 4 if rarity == "ssr" else BORDER_MARGIN
    a[:m, :] = 0
    a[-m:, :] = 0
    a[:, :m] = 0
    a[:, -m:] = 0

    b = (a > EDGE_THR).astype(np.uint8)

    # 枠直線の除去（背景がまだ残る場合に効く）
    row_sum = b.sum(axis=1)
    col_sum = b.sum(axis=0)
    W = b.shape[1]
    H = b.shape[0]
    b[row_sum > int(LINE_RATIO * W), :] = 0
    b[:, col_sum > int(LINE_RATIO * H)] = 0

    return np.packbits(b.flatten())


def build_ref_bank(ref_root: Path):
    """
    bank[rarity] = list of {kind, bits}
    """
    bank = {r: [] for r in RARITIES}

    if not ref_root.exists():
        raise FileNotFoundError(f"REF_ROOT not found: {ref_root.resolve()}")

    for d in [p for p in ref_root.iterdir() if p.is_dir()]:
        rarity = parse_rarity(d.name)
        kind = parse_kind(d.name)

        # 拡張子大小/下階層にも強く拾う
        pngs = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() == ".png"]
        print(f"[DEBUG] REF {d.name} -> rarity={rarity}, kind={kind}, png={len(pngs)}")

        if rarity is None or kind is None:
            continue

        for p in pngs:
            try:
                bits = marker_binary(p, rarity=rarity)
                bank[rarity].append({"kind": kind, "bits": bits})
            except Exception as e:
                print(f"[WARN] ref skip: {p} err={e}")

    for r in RARITIES:
        if not bank[r]:
            print(f"[WARN] 参照が空: {r}")

    if all(len(bank[r]) == 0 for r in RARITIES):
        raise FileNotFoundError(f"参照画像が1枚も読み込めませんでした。REF_ROOT={ref_root.resolve()}")

    return bank


def predict_kind(bits_test: np.ndarray, bank_r: list[dict], topk: int = TOPK) -> tuple[str, int]:
    """
    距離が小さいほど強い票で投票
    + 最良距離のTHRESH_RATIO倍以内だけ投票（遠い候補混入を防ぐ）
    戻り値: (pred_kind, best_distance)
    """
    scored = []
    for item in bank_r:
        d = hamming_bytes(bits_test, item["bits"])
        scored.append((d, item["kind"]))

    scored.sort(key=lambda x: x[0])
    top = scored[:topk]

    d0 = top[0][0]
    thresh = int(d0 * THRESH_RATIO) + 1
    top = [(d, k) for (d, k) in top if d <= thresh]

    vote = defaultdict(float)
    for d, k in top:
        vote[k] += 1.0 / (1e-6 + d)

    pred = max(vote.items(), key=lambda x: x[1])[0]
    return pred, d0


def main():
    print("[DEBUG] REF_ROOT =", REF_ROOT.resolve(), "exists=", REF_ROOT.exists())
    print("[DEBUG] TEST_ROOT=", TEST_ROOT.resolve(), "exists=", TEST_ROOT.exists())

    bank = build_ref_bank(REF_ROOT)

    # テスト側（拡張子大小/下階層もOK）
    test_paths = [p for p in TEST_ROOT.rglob("*") if p.is_file() and p.suffix.lower() == ".png"]
    test_paths = sorted(test_paths)
    if not test_paths:
        raise FileNotFoundError(f"テスト画像が見つかりません: {TEST_ROOT.resolve()}")

    rows = []
    for p in test_paths:
        true_dir = p.parent.name
        rarity = parse_rarity(true_dir)      # 本番は「あなたの100%判定結果」を入れてOK
        true_kind = parse_kind(true_dir)

        try:
            bits = marker_binary(p, rarity=rarity)
        except Exception as e:
            print(f"[ERROR] marker_binary failed: {p} err={e}")
            continue

        # rarityが取れない/参照が薄い場合は全参照でフォールバック
        if rarity is None or not bank.get(rarity):
            merged = []
            for r in RARITIES:
                merged.extend(bank[r])
            pred_kind, best_d = predict_kind(bits, merged, topk=TOPK)
        else:
            pred_kind, best_d = predict_kind(bits, bank[rarity], topk=TOPK)

        correct = 1 if (true_kind is not None and pred_kind == true_kind) else 0

        rows.append({
            "テストファイル名": p.name,
            "ディレクトリ": true_dir,
            "予測種類": pred_kind,
            "正誤": correct,
            "best_hamming": best_d,  # デバッグ用（不要なら消してOK）
        })

    df = pd.DataFrame(rows)

    print("Overall kind acc:", df["正誤"].mean())
    print(df.groupby("ディレクトリ")["正誤"].mean().sort_values(ascending=False))

    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print("Saved:", OUT_CSV)


if __name__ == "__main__":
    main()
