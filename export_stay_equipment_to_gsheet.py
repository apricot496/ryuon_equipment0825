# export_stay_equipment_to_gsheet.py
# ------------------------------------------------------------
# stay_equipment を「equipment_img_scraping の新規」で完全上書きし、
# 装備種別が空のものだけ（装備名NOT NULL）を UR/KSR のみ自動判定して埋め、
# Google Spreadsheet の stay_equipment シートへ全量上書きする。
#
# 依存:
#   pip install gspread google-auth pandas python-dotenv pillow numpy
# ------------------------------------------------------------

import os
import sqlite3
from pathlib import Path
from collections import defaultdict
import unicodedata

import numpy as np
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image, ImageFilter, ImageOps
from dotenv import load_dotenv

# =====================
# ユーザー提供：認証情報読み込み
# =====================
def load_credentials_and_key():
    """ローカルなら .env から、GitHub Actions なら Secrets から読み込む"""
    if os.getenv("GITHUB_ACTIONS") == "true":
        spreadsheet_key = os.environ["SPREADSHEET_KEY_NAME"]
        creds_info = {
            "type": os.environ["GCP_TYPE"],
            "project_id": os.environ["GCP_PROJECT_ID"],
            "private_key_id": os.environ["GCP_PRIVATE_KEY_ID"],
            "private_key": os.environ["GCP_PRIVATE_KEY"].replace("\\n", "\n"),
            "client_email": os.environ["GCP_CLIENT_EMAIL"],
            "client_id": os.environ["GCP_CLIENT_ID"],
            "auth_uri": os.environ["GCP_AUTH_URI"],
            "token_uri": os.environ["GCP_TOKEN_URI"],
            "auth_provider_x509_cert_url": os.environ["GCP_AUTH_PROVIDER_CERT_URL"],
            "client_x509_cert_url": os.environ["GCP_CLIENT_CERT_URL"],
            "universe_domain": os.environ["GCP_UNIVERSE_DOMAIN"],
        }
    else:
        load_dotenv()
        spreadsheet_key = os.getenv("SPREADSHEET_KEY_NAME")
        creds_info = {
            "type": os.getenv("GCP_TYPE"),
            "project_id": os.getenv("GCP_PROJECT_ID"),
            "private_key_id": os.getenv("GCP_PRIVATE_KEY_ID"),
            "private_key": os.getenv("GCP_PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.getenv("GCP_CLIENT_EMAIL"),
            "client_id": os.getenv("GCP_CLIENT_ID"),
            "auth_uri": os.getenv("GCP_AUTH_URI"),
            "token_uri": os.getenv("GCP_TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("GCP_AUTH_PROVIDER_CERT_URL"),
            "client_x509_cert_url": os.getenv("GCP_CLIENT_CERT_URL"),
            "universe_domain": os.getenv("GCP_UNIVERSE_DOMAIN"),
        }

    return creds_info, spreadsheet_key


# =====================
# 設定
# =====================
DB_PATH = Path("equipment.db")

SRC_TABLE = "equipment_img_scraping"
DST_TABLE = "stay_equipment"
SHEET_NAME = "stay_equipment"

# 自動判定するレア（それ以外は装備種別を埋めない）
ALLOWED_RARITIES = {"UR", "KSR"}

# Sheet/DBの列順
COLUMNS = [
    "装備名",
    "レアリティ",
    "装備種別",
    "体力",
    "攻撃力",
    "防御力",
    "会心率",
    "回避率",
    "命中率",
    "アビリティ",
    "IMG_URL",
]

# マーク特徴抽出（左上）
ROI_X0, ROI_Y0 = 0.00, 0.00
ROI_X1, ROI_Y1 = 0.38, 0.38
EDGE_THR = 35
BORDER_MARGIN = 5
LINE_RATIO = 0.70

# kNN
TOPK = 9

# 低信頼は埋めない（事故防止）
HOLD_MAX_BEST = 650
HOLD_MIN_GAP = 30

# 高速Hamming
_BITCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
KIND_TO_ID = {"武器": 0, "防具": 1, "装飾": 2}
ID_TO_KIND = {0: "武器", 1: "防具", 2: "装飾"}


# =====================
# Utility
# =====================
def norm_text(s: str | None) -> str:
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", str(s))

def norm_rarity(s: str | None) -> str:
    t = norm_text(s).upper()
    t = t.replace("_", "").replace(" ", "").replace("　", "")
    return t

def norm_table_name(s: str) -> str:
    t = unicodedata.normalize("NFKC", s).lower()
    t = t.replace("_", "").replace(" ", "").replace("　", "")
    return t

def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None

def col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return any(row[1] == col for row in cur.fetchall())


# =====================
# stay_equipment 作成
# =====================
def ensure_stay_equipment_table(conn: sqlite3.Connection):
    ddl = f"""
    CREATE TABLE IF NOT EXISTS "{DST_TABLE}" (
      "装備名"     TEXT,
      "レアリティ"  TEXT,
      "装備種別"   TEXT,
      "体力"       INTEGER,
      "攻撃力"     INTEGER,
      "防御力"     INTEGER,
      "会心率"     REAL,
      "回避率"     REAL,
      "命中率"     REAL,
      "アビリティ"  TEXT,
      "IMG_URL"    TEXT,
      PRIMARY KEY ("装備名","レアリティ")
    );
    """
    conn.execute(ddl)
    conn.commit()


# =====================
# stay_equipment を完全上書き（scrapingの新規で作り直し）
# =====================
def refresh_stay_equipment_from_scraping(conn: sqlite3.Connection):
    """
    stay_equipment を毎回「equipment_img_scraping の新規」で完全上書きする。
    - 新規フラグ列があれば 新規フラグ=1 のみ
    - 無ければ全件
    - 装備種別は一旦 ""（後段でUR/KSRのみ埋める）
    """
    ensure_stay_equipment_table(conn)

    if not table_exists(conn, SRC_TABLE):
        raise FileNotFoundError(f"table not found: {SRC_TABLE}")

    has_new_flag = col_exists(conn, SRC_TABLE, "新規フラグ")
    where_new = 'WHERE "新規フラグ" = 1' if has_new_flag else ""

    # 1) 全消し
    conn.execute(f'DELETE FROM "{DST_TABLE}"')

    # 2) 全投入（完全上書き）
    rows = conn.execute(
        f'''
        SELECT
          装備名, レアリティ, 体力, 攻撃力, 防御力, 会心率, 回避率, 命中率, アビリティ, IMG_URL
        FROM "{SRC_TABLE}"
        {where_new}
        '''
    ).fetchall()

    # 装備名がNULL/空のものは落とす
    to_insert = []
    for r in rows:
        name = r["装備名"]
        if name is None or str(name).strip() == "":
            continue
        to_insert.append((
            name,
            r["レアリティ"],
            "",   # ★ここ：None -> ""（NOT NULL制約回避）
            r["体力"], r["攻撃力"], r["防御力"],
            r["会心率"], r["回避率"], r["命中率"],
            r["アビリティ"],
            r["IMG_URL"],
        ))

    before = conn.total_changes
    if to_insert:
        conn.executemany(
            f'''
            INSERT INTO "{DST_TABLE}"
            (装備名, レアリティ, 装備種別, 体力, 攻撃力, 防御力, 会心率, 回避率, 命中率, アビリティ, IMG_URL)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            to_insert
        )
    conn.commit()
    inserted = conn.total_changes - before

    print("\n[STAY REFRESH]")
    print("source rows:", len(rows))
    print("inserted to stay:", inserted)
    print("mode:", "新規フラグ=1 のみ" if has_new_flag else "新規フラグ列なし → 全件")


# =====================
# 参照テーブルの自動検出（初回からバンクが作れる）
# =====================
def discover_reference_tables(conn: sqlite3.Connection):
    """
    DB内のテーブル名から、(table_name, rarity, kind) を抽出。
    対象例: ur武器 / ur_武器 / ksr防具 / ksr_装飾 など
    必須列: 装備名
    """
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]

    ref = []
    for t in tables:
        if t in (SRC_TABLE, DST_TABLE):
            continue

        tn = norm_table_name(t)

        # 種別
        kind = None
        if "武器" in t:
            kind = "武器"
        elif "防具" in t:
            kind = "防具"
        elif "装飾" in t:
            kind = "装飾"
        if kind is None:
            continue

        # レアリティ（テーブル名から推定）
        rarity = None
        if "ur" in tn:
            rarity = "UR"
        elif "ksr" in tn:
            rarity = "KSR"
        elif "ssr" in tn:
            rarity = "SSR"

        # バンクはUR/KSRだけで十分
        if rarity not in ALLOWED_RARITIES:
            continue

        if not col_exists(conn, t, "装備名"):
            continue

        ref.append((t, rarity, kind))

    if not ref:
        raise RuntimeError(
            "参照テーブル（例: ur武器 / ksr防具 等）が見つかりませんでした。"
            "テーブル名に『ur/ksr』と『武器/防具/装飾』が含まれ、装備名列がある必要があります。"
        )
    return ref


def build_labeled_keyset_from_ref_tables(conn: sqlite3.Connection):
    """
    参照テーブル群から、(装備名, レアリティ) -> 装備種別 を構築。
    - 参照テーブルにレアリティ列があればそれを使う
    - なければテーブル名から補完
    """
    ref_tables = discover_reference_tables(conn)
    key_to_kind: dict[tuple[str, str], str] = {}

    for t, rarity_from_name, kind in ref_tables:
        has_rarity_col = col_exists(conn, t, "レアリティ")
        if has_rarity_col:
            rows = conn.execute(f'SELECT 装備名, レアリティ FROM "{t}"').fetchall()
            for name, rarity in rows:
                rr = norm_rarity(rarity)
                if rr not in ALLOWED_RARITIES:
                    continue
                key_to_kind.setdefault((name, rr), kind)
        else:
            rows = conn.execute(f'SELECT 装備名 FROM "{t}"').fetchall()
            for (name,) in rows:
                key_to_kind.setdefault((name, rarity_from_name), kind)

    if not key_to_kind:
        raise RuntimeError("参照テーブルからラベル付きキーが作れませんでした（参照側が空の可能性）。")
    return key_to_kind


# =====================
# マーク特徴抽出 / 予測
# =====================
def marker_binary(img_path: str) -> np.ndarray:
    with Image.open(img_path) as im:
        im = im.convert("RGBA")
        w, h = im.size

        x0 = int(ROI_X0 * w)
        y0 = int(ROI_Y0 * h)
        x1 = max(x0 + 1, int(ROI_X1 * w))
        y1 = max(y0 + 1, int(ROI_Y1 * h))

        roi = im.crop((x0, y0, x1, y1)).convert("RGB")

    roi = roi.resize((64, 64), Image.Resampling.LANCZOS)
    roi = ImageOps.autocontrast(roi)
    edge = roi.convert("L").filter(ImageFilter.FIND_EDGES)

    a = np.asarray(edge, dtype=np.uint8).copy()
    m = BORDER_MARGIN
    a[:m, :] = 0
    a[-m:, :] = 0
    a[:, :m] = 0
    a[:, -m:] = 0

    b = (a > EDGE_THR).astype(np.uint8)

    row_sum = b.sum(axis=1)
    col_sum = b.sum(axis=0)
    W = b.shape[1]
    H = b.shape[0]
    b[row_sum > int(LINE_RATIO * W), :] = 0
    b[:, col_sum > int(LINE_RATIO * H)] = 0

    return np.packbits(b.flatten())


def hamming_bytes_vec(bits_mat: np.ndarray, bits_test: np.ndarray) -> np.ndarray:
    xor = np.bitwise_xor(bits_mat, bits_test[None, :])
    return _BITCOUNT[xor].sum(axis=1).astype(np.int32)


def predict_kind(bits_test: np.ndarray, bits_mat: np.ndarray, kind_ids: np.ndarray):
    dists = hamming_bytes_vec(bits_mat, bits_test)
    order = np.argsort(dists)

    best = int(dists[order[0]])
    second = int(dists[order[1]]) if len(order) > 1 else best
    gap = second - best

    top = order[:TOPK]
    vote = defaultdict(float)
    for idx in top:
        k = int(kind_ids[idx])
        d = float(dists[idx])
        vote[k] += 1.0 / (1e-6 + d)

    pred_id = max(vote.items(), key=lambda x: x[1])[0]
    return ID_TO_KIND[pred_id], best, gap


def build_banks_from_ref_tables(conn: sqlite3.Connection):
    """
    初回から作れる参照バンク：
    - ラベル（武器/防具/装飾）は参照テーブル（ur武器/ksr防具/...）から
    - 画像は equipment_img_scraping.IMG_Path を (装備名,レアリティ) で引く
    """
    key_to_kind = build_labeled_keyset_from_ref_tables(conn)

    cur = conn.execute(
        f'''
        SELECT 装備名 AS name, レアリティ AS rarity, IMG_Path AS img_path
          FROM "{SRC_TABLE}"
         WHERE IMG_Path IS NOT NULL AND IMG_Path != ""
        '''
    )

    tmp = {r: {"bits": [], "ids": []} for r in ALLOWED_RARITIES}

    for row in cur.fetchall():
        name = row[0]
        rarity = norm_rarity(row[1])
        img_path = row[2]

        if rarity not in ALLOWED_RARITIES:
            continue

        kind = key_to_kind.get((name, rarity))
        if kind not in KIND_TO_ID:
            continue

        p = Path(img_path)
        if not p.exists():
            continue

        try:
            bits = marker_binary(str(p))
        except Exception:
            continue

        tmp[rarity]["bits"].append(bits)
        tmp[rarity]["ids"].append(KIND_TO_ID[kind])

    banks = {}
    for rarity in ALLOWED_RARITIES:
        if tmp[rarity]["bits"]:
            banks[rarity] = (
                np.stack(tmp[rarity]["bits"], axis=0),
                np.array(tmp[rarity]["ids"], dtype=np.int16),
            )

    for r in sorted(ALLOWED_RARITIES):
        if r in banks:
            print(f"[INFO] bank[{r}] size:", banks[r][0].shape[0])
        else:
            print(f"[WARN] bank[{r}] empty（参照表とscrapingのキー不一致 or IMG_Path不足の可能性）")

    if not banks:
        raise RuntimeError(
            "参照バンクが空です。"
            "参照テーブル（ur武器等）と equipment_img_scraping の (装備名,レアリティ) が一致し、IMG_Path が存在する必要があります。"
        )

    return banks


def build_scraping_imgpath_map(conn: sqlite3.Connection):
    """(装備名, レアリティ) -> IMG_Path の辞書"""
    cur = conn.execute(
        f'''
        SELECT 装備名 AS name, レアリティ AS rarity, IMG_Path AS img_path
          FROM "{SRC_TABLE}"
         WHERE IMG_Path IS NOT NULL AND IMG_Path != ""
        '''
    )
    mp: dict[tuple[str, str], str] = {}
    for name, rarity, img_path in cur.fetchall():
        rr = norm_rarity(rarity)
        mp[(name, rr)] = img_path
    return mp


# =====================
# stay_equipment 更新（装備種別NULL/空 かつ 装備名NOT NULL/空 のみ）
# =====================
def update_stay_equipment_only_null_kind(conn: sqlite3.Connection):
    banks = build_banks_from_ref_tables(conn)
    img_map = build_scraping_imgpath_map(conn)

    tgt = conn.execute(
        f'''
        SELECT rowid AS rid, 装備名, レアリティ
          FROM "{DST_TABLE}"
         WHERE (装備種別 IS NULL OR TRIM(装備種別) = "")
           AND 装備名 IS NOT NULL AND TRIM(装備名) != ""
        '''
    ).fetchall()

    updated = 0
    skipped_rarity = 0
    skipped_no_bank = 0
    skipped_no_img = 0
    skipped_low_conf = 0
    skipped_io = 0

    updates = []

    for rid, name, rarity_raw in tgt:
        rarity = norm_rarity(rarity_raw)

        # 自動判定はUR/KSRのみ
        if rarity not in ALLOWED_RARITIES:
            skipped_rarity += 1
            continue

        if rarity not in banks:
            skipped_no_bank += 1
            continue

        img_path = img_map.get((name, rarity))
        if not img_path:
            skipped_no_img += 1
            continue

        p = Path(img_path)
        if not p.exists():
            skipped_io += 1
            continue

        try:
            bits = marker_binary(str(p))
        except Exception:
            skipped_io += 1
            continue

        bits_mat, kind_ids = banks[rarity]
        pred_kind, best, gap = predict_kind(bits, bits_mat, kind_ids)

        if best >= HOLD_MAX_BEST or gap <= HOLD_MIN_GAP:
            skipped_low_conf += 1
            continue

        updates.append((pred_kind, rid))

    if updates:
        before = conn.total_changes
        conn.executemany(
            f'UPDATE "{DST_TABLE}" SET 装備種別 = ? WHERE rowid = ?',
            updates
        )
        conn.commit()
        updated = conn.total_changes - before

    print("\n[STAY KIND UPDATE]")
    print("target rows (null kind):", len(tgt))
    print("updated:", updated)
    print("skipped (rarity_not_allowed):", skipped_rarity)
    print("skipped (bank_missing_for_rarity):", skipped_no_bank)
    print("skipped (no_IMG_Path_match):", skipped_no_img)
    print("skipped (low_confidence):", skipped_low_conf)
    print("skipped (img_missing_or_error):", skipped_io)


def read_stay_equipment(conn: sqlite3.Connection) -> pd.DataFrame:
    cols_sql = ", ".join([f'"{c}"' for c in COLUMNS])
    df = pd.read_sql_query(f'SELECT {cols_sql} FROM "{DST_TABLE}"', conn)
    if "レアリティ" in df.columns and "装備名" in df.columns:
        df = df.sort_values(["レアリティ", "装備名"], kind="mergesort").reset_index(drop=True)
    return df


# =====================
# Google Sheets 書き込み
# =====================
def get_spreadsheet():
    creds_info, spreadsheet_key = load_credentials_and_key()
    if not spreadsheet_key:
        raise ValueError("SPREADSHEET_KEY_NAME が設定されていません")

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_key)
    return sh


def upsert_worksheet(sh, title: str, rows: int, cols: int):
    try:
        ws = sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=max(rows, 100), cols=max(cols, 20))
    return ws


def overwrite_sheet(ws, df: pd.DataFrame):
    df2 = df.copy()
    df2 = df2.where(pd.notnull(df2), "")

    values = [df2.columns.tolist()] + df2.values.tolist()

    ws.clear()
    ws.resize(rows=len(values), cols=len(values[0]) if values else len(COLUMNS))
    if values:
        ws.update("A1", values, value_input_option="RAW")

    try:
        ws.freeze(rows=1)
    except Exception:
        pass


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH.resolve()}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, SRC_TABLE):
            raise FileNotFoundError(f"table not found: {SRC_TABLE}")

        # 1) stay_equipment を scrapingの新規で完全上書き
        refresh_stay_equipment_from_scraping(conn)

        # 2) stay_equipment の「装備種別が空」のみ、自動判定で更新（UR/KSRのみ）
        update_stay_equipment_only_null_kind(conn)

        # 3) stay_equipment 読み出し
        df = read_stay_equipment(conn)
        print(f"\n[EXPORT] stay_equipment rows: {len(df)}")

    finally:
        conn.close()

    # 4) Sheets へ全量上書き（なければ作成）
    sh = get_spreadsheet()
    ws = upsert_worksheet(sh, SHEET_NAME, rows=len(df) + 1, cols=len(COLUMNS))
    overwrite_sheet(ws, df)
    print(f"[OK] wrote to sheet: {SHEET_NAME}")


if __name__ == "__main__":
    main()
