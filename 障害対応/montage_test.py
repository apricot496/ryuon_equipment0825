from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image, ImageFilter
from collections import defaultdict

# ========= パス =========
TEST_ROOT = Path("モンタージュ判定テスト用")
REF_ROOT  = Path("モンタージュ作成用")
OUT_CSV = Path("montage_nn_2axis_test.csv")

IMG_EXTS = [".png"]  # 必要なら増やす

# ========= 前処理/特徴量設定 =========
TARGET_SIZE = 64
W_HASH = 0.45
W_EDGE = 0.45
W_HIST = 0.10


def normalize_label(s: str) -> str:
    s = s.lower()
    for ch in ["_", " ", "　", "-", "‐", "—", "－"]:
        s = s.replace(ch, "")
    return s


def split_rarity_kind(label: str):
    """
    例: 'ur武器' / 'ur_武器' / 'UR装飾' -> ('ur', '武器')
    """
    raw = label
    s = normalize_label(label)

    # rarity
    rarity = None
    for r in ["ur", "ksr", "ssr"]:
        if r in s:
            rarity = r
            break

    # kind
    kind = None
    if "武器" in raw:
        kind = "武器"
    elif "防具" in raw:
        kind = "防具"
    elif "装飾" in raw:
        kind = "装飾"

    return rarity, kind


def content_crop_and_resize(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    arr = np.array(im)
    alpha = arr[..., 3]

    mask = alpha > 0
    if mask.any():
        ys, xs = np.where(mask)
    else:
        rgb = arr[..., :3].astype(np.int16)
        corners = np.stack([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]], axis=0)
        bg = corners.mean(axis=0)
        dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
        mask2 = dist > 18  # 背景が残るなら↑、欠けるなら↓
        if mask2.any():
            ys, xs = np.where(mask2)
        else:
            return im.convert("RGB").resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)

    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    h = y1 - y0 + 1
    w = x1 - x0 + 1

    pad = int(0.12 * max(h, w))  # 防具が弱いならここ効きやすい
    y0 = max(0, y0 - pad)
    x0 = max(0, x0 - pad)
    y1 = min(arr.shape[0] - 1, y1 + pad)
    x1 = min(arr.shape[1] - 1, x1 + pad)

    cropped = im.crop((x0, y0, x1 + 1, y1 + 1))

    cw, ch = cropped.size
    side = max(cw, ch)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(cropped, ((side - cw) // 2, (side - ch) // 2))
    return canvas.convert("RGB").resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)


def dhash64(im_rgb: Image.Image) -> int:
    g = im_rgb.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    diff = (a[:, 1:] > a[:, :-1]).astype(np.uint8).flatten()
    h = 0
    for b in diff:
        h = (h << 1) | int(b)
    return h


def hsv_hist(im_rgb: Image.Image, bins=(8, 4, 4)) -> np.ndarray:
    hsv = np.asarray(im_rgb.convert("HSV"), dtype=np.uint8)
    flat = hsv.reshape(-1, 3)
    hist, _ = np.histogramdd(flat, bins=bins, range=((0, 255), (0, 255), (0, 255)))
    hist = hist.astype(np.float32).flatten()
    s = hist.sum()
    return hist / s if s > 0 else hist


def chi2(a: np.ndarray, b: np.ndarray, eps=1e-6) -> float:
    return float(0.5 * np.sum(((a - b) ** 2) / (a + b + eps)))


def ham(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def extract_features(path: Path):
    with Image.open(path) as im:
        x = content_crop_and_resize(im)
    h1 = dhash64(x)
    edge = x.filter(ImageFilter.FIND_EDGES)
    h2 = dhash64(edge)
    hist = hsv_hist(x)
    return h1, h2, hist


def build_reference(ref_root: Path):
    refs = []
    for d in sorted([p for p in ref_root.iterdir() if p.is_dir()]):
        label = d.name
        for ext in IMG_EXTS:
            for p in d.glob(f"*{ext}"):
                try:
                    h1, h2, hist = extract_features(p)
                    refs.append({"label": label, "path": p, "hash": h1, "edge": h2, "hist": hist})
                except Exception:
                    continue
    if not refs:
        raise FileNotFoundError(f"参照画像が見つかりません: {ref_root}/***/***.png")
    return refs


def predict_one_knn(test_path: Path, refs, k: int = 7):
    th1, th2, thist = extract_features(test_path)

    scored = []
    for r in refs:
        d1 = ham(th1, r["hash"]) / 64.0
        d2 = ham(th2, r["edge"]) / 64.0
        d3 = chi2(thist, r["hist"])
        score = W_HASH * d1 + W_EDGE * d2 + W_HIST * d3
        scored.append((score, r["label"]))

    scored.sort(key=lambda x: x[0])
    topk = scored[:k]

    eps = 1e-6
    vote = defaultdict(float)
    for s, lab in topk:
        vote[lab] += 1.0 / (eps + s)

    pred = max(vote.items(), key=lambda x: x[1])[0]
    return pred, topk[0][0]


def main():
    if not TEST_ROOT.exists():
        raise FileNotFoundError(f"テストルートが見つかりません: {TEST_ROOT}")
    if not REF_ROOT.exists():
        raise FileNotFoundError(f"参照ルートが見つかりません: {REF_ROOT}")

    refs = build_reference(REF_ROOT)

    test_paths = []
    for ext in IMG_EXTS:
        test_paths.extend(TEST_ROOT.glob(f"*/*{ext}"))
    test_paths = sorted([p for p in test_paths if p.is_file()])
    if not test_paths:
        raise FileNotFoundError(f"テスト画像が見つかりません: {TEST_ROOT}/***/***.png")

    rows = []
    for p in test_paths:
        true_dir = p.parent.name  # 正解ラベルはディレクトリ名
        pred_dir, _ = predict_one_knn(p, refs, k=7)

        true_r, true_k = split_rarity_kind(true_dir)
        pred_r, pred_k = split_rarity_kind(pred_dir)

        rarity_ok = 1 if (true_r is not None and pred_r is not None and true_r == pred_r) else 0
        kind_ok   = 1 if (true_k is not None and pred_k is not None and true_k == pred_k) else 0
        both_ok   = 1 if (rarity_ok == 1 and kind_ok == 1) else 0

        rows.append({
            "テストファイル名": p.name,
            "ディレクトリ": true_dir,
            "対象montage_img": f"montage_{pred_dir}.png",
            "レアリティ一致": rarity_ok,
            "種類一致": kind_ok,
            "両方一致": both_ok,  # 不要なら消してOK
        })

    df = pd.DataFrame(rows)

    print("=== Overall ===")
    print("レアリティ一致:", df["レアリティ一致"].mean())
    print("種類一致      :", df["種類一致"].mean())
    print("両方一致      :", df["両方一致"].mean())

    # 軸別の内訳（見たいとき）
    df["true_rarity"], df["true_kind"] = zip(*df["ディレクトリ"].map(split_rarity_kind))
    print("\n=== By rarity (both axis) ===")
    print(df.groupby("true_rarity")[["レアリティ一致", "種類一致", "両方一致"]].mean())

    print("\n=== By kind (both axis) ===")
    print(df.groupby("true_kind")[["レアリティ一致", "種類一致", "両方一致"]].mean())

    df.drop(columns=["true_rarity", "true_kind"]).to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {OUT_CSV}")


if __name__ == "__main__":
    main()
