from __future__ import annotations

import argparse
from pathlib import Path
import os
import re

import numpy as np
import pandas as pd
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv


DB_URL = "sqlite:///./equipment.db"

FIX_TABLES = [
    "ssr武器", "ssr防具", "ssr装飾",
    "ksr武器", "ksr防具", "ksr装飾",
    "ur武器", "ur防具", "ur装飾",
]

# 元の差分抽出で必要なカラム（non_check_df のベース）
BASE_COLUMNS = [
    "装備名",
    "レアリティ",
    "体力",
    "攻撃力",
    "防御力",
    "会心率",
    "回避率",
    "命中率",
    "アビリティ",
]

# 書き込み時のカラム順（要件）
DESIRED_COLUMNS = [
    "装備名",
    "装備番号",
    "レアリティ",
    "体力",
    "攻撃力",
    "防御力",
    "会心率",
    "回避率",
    "命中率",
    "アビリティ",
    "アビリティカテゴリ",
    "装備種類",
]

# --- 画像判定パラメータ ---
ICON_CROP_RATIO = 0.32
ICON_NORM_SIZE = (32, 32)
MSE_THRESHOLD = 2500.0
UNKNOWN_LABEL = "不明"

# --- アビリティ分割（複数アビリティがセルに入る場合） ---
ABILITY_SPLIT_RE = re.compile(r"\s*/\s*|\s*／\s*|\s*,\s*|\s*、\s*\n\s*|\s*\n\s*")

# --- 装備番号コード ---
TYPE_CODE = {"武器": 0, "防具": 1, "装飾": 2}
RARITY_CODE = {"UR": 0, "KSR": 1, "SSR": 2}


# =========================
# Utility: column reorder & dtype
# =========================
def reorder_columns_for_output(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in DESIRED_COLUMNS:
        if c not in out.columns:
            out[c] = pd.NA
    ordered = out[DESIRED_COLUMNS]
    extra_cols = [c for c in out.columns if c not in DESIRED_COLUMNS]
    if extra_cols:
        ordered = pd.concat([ordered, out[extra_cols]], axis=1)
    return ordered


def enforce_nullable_int_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    体力/攻撃力/防御力 を「0とNULLを区別できる」NULL許容の整数(Int64)にする。
    """
    out = df.copy()
    for col in ["体力", "攻撃力", "防御力"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    return out


# =========================
# SQLite helpers
# =========================
def _table_exists(engine: Engine, table_name: str) -> bool:
    sql = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1"
    with engine.connect() as conn:
        row = conn.exec_driver_sql(sql, (table_name,)).fetchone()
    return row is not None


def _read_sql_table(engine: Engine, table_name: str) -> pd.DataFrame:
    return pd.read_sql_query(f'SELECT * FROM "{table_name}"', con=engine)


def resolve_non_check_sheet_and_table(engine: Engine) -> tuple[str, str]:
    default = ("non_check_equipments", "non_check_equipments")
    if not _table_exists(engine, "staying_check_equipment_list"):
        return default

    df = _read_sql_table(engine, "staying_check_equipment_list")

    sheet_cols = [c for c in ["sheet_name", "sheet", "シート名"] if c in df.columns]
    table_cols = [c for c in ["table_name", "table", "テーブル名"] if c in df.columns]
    if not sheet_cols or not table_cols:
        return default

    sheet_col = sheet_cols[0]
    table_col = table_cols[0]

    hit = df[df[table_col].astype(str) == "non_check_equipments"]
    if len(hit) > 0:
        return (str(hit.iloc[0][sheet_col]), str(hit.iloc[0][table_col]))

    hit = df[df[table_col].astype(str).str.contains("non_check", case=False, na=False)]
    if len(hit) > 0:
        return (str(hit.iloc[0][sheet_col]), str(hit.iloc[0][table_col]))

    return default


def upsert_non_check_to_sqlite(engine: Engine, df: pd.DataFrame, table_name: str) -> None:
    """
    SQLite に書き込む（簡易upsert）
    キー: (装備名, レアリティ)
    """
    if not _table_exists(engine, table_name):
        df.head(0).to_sql(table_name, con=engine, if_exists="replace", index=False)

    keys = df[["装備名", "レアリティ"]].dropna().drop_duplicates()

    with engine.begin() as conn:
        for name, rarity in keys.itertuples(index=False):
            conn.exec_driver_sql(
                f'DELETE FROM "{table_name}" WHERE "装備名" = ? AND "レアリティ" = ?',
                (name, rarity),
            )

    df.to_sql(table_name, con=engine, if_exists="append", index=False)


# =========================
# Build non_check_df
# =========================
def load_fix_equipments_df(engine: Engine) -> pd.DataFrame:
    dfs = [_read_sql_table(engine, t) for t in FIX_TABLES]
    fix_df = pd.concat(dfs, ignore_index=True)
    return fix_df.drop_duplicates(subset=["装備名", "レアリティ"], keep="first").reset_index(drop=True)


def build_non_check_candidates_df(engine: Engine) -> pd.DataFrame:
    fix_df = load_fix_equipments_df(engine)
    fix_keys = fix_df[["装備名", "レアリティ"]].drop_duplicates()

    scraped_df = _read_sql_table(engine, "equipment_img_scraping")

    merged = scraped_df.merge(
        fix_keys,
        on=["装備名", "レアリティ"],
        how="left",
        indicator=True,
    )
    non_check_df = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])
    non_check_df = non_check_df.drop_duplicates(subset=["装備名", "レアリティ"], keep="first")
    return non_check_df[BASE_COLUMNS].reset_index(drop=True)


# =========================
# Image -> 装備種類 (武器/防具/装飾)
# =========================
def _load_icon_patch(img_path: Path) -> np.ndarray:
    with Image.open(img_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        r = ICON_CROP_RATIO
        crop_w = max(1, int(w * r))
        crop_h = max(1, int(h * r))
        patch = im.crop((0, 0, crop_w, crop_h)).resize(ICON_NORM_SIZE, Image.Resampling.BILINEAR)
        patch = patch.convert("L")
    return np.asarray(patch, dtype=np.float32)


def _mse(a: np.ndarray, b: np.ndarray) -> float:
    d = a - b
    return float(np.mean(d * d))


def find_reference_images(engine: Engine, static_dir: Path) -> dict[str, Path]:
    table_by_type = {
        "武器": ["ur武器", "ssr武器", "ksr武器"],
        "防具": ["ur防具", "ssr防具", "ksr防具"],
        "装飾": ["ur装飾", "ssr装飾", "ksr装飾"],
    }

    refs: dict[str, Path] = {}
    for equip_type, tables in table_by_type.items():
        found: Path | None = None

        for t in tables:
            df = _read_sql_table(engine, t)
            for _, row in df[["装備名", "レアリティ"]].dropna().iterrows():
                p = static_dir / f'{row["装備名"]}_{row["レアリティ"]}.png'
                if p.exists():
                    found = p
                    break
            if found is not None:
                break

        if found is None:
            raise FileNotFoundError(
                f"{equip_type} の参照画像が static_dir={static_dir} に見つかりませんでした。"
            )

        refs[equip_type] = found

    return refs


def build_reference_icons(ref_paths: dict[str, Path]) -> dict[str, np.ndarray]:
    return {label: _load_icon_patch(path) for label, path in ref_paths.items()}


def infer_equip_type_from_image(img_path: Path, refs: dict[str, np.ndarray]) -> str:
    if not img_path.exists():
        return UNKNOWN_LABEL

    patch = _load_icon_patch(img_path)
    scores = {label: _mse(patch, ref_patch) for label, ref_patch in refs.items()}
    best_label = min(scores, key=scores.get)
    if scores[best_label] > MSE_THRESHOLD:
        return UNKNOWN_LABEL
    return best_label


def add_equip_type_column(non_check_df: pd.DataFrame, static_dir: Path, refs: dict[str, np.ndarray]) -> pd.DataFrame:
    out = non_check_df.copy()

    def _infer_row(row: pd.Series) -> str:
        img_path = static_dir / f'{row["装備名"]}_{row["レアリティ"]}.png'
        return infer_equip_type_from_image(img_path, refs)

    out["装備種類"] = out.apply(_infer_row, axis=1)
    return out


# =========================
# Ability -> アビリティカテゴリ (rule-based)
# =========================
def _compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    compiled: list[re.Pattern] = []
    for p in patterns:
        p = p.strip()
        if not p:
            continue
        esc = re.escape(p)
        esc = esc.replace(r"\*\*\*\*", r".{0,20}")
        esc = esc.replace(r"\*\*\*", r".{0,20}")
        esc = esc.replace("%", r"[%％]?")
        compiled.append(re.compile(esc))
    return compiled


RAW_RULES: dict[str, list[str]] = {
    "BSCT加速": ["スキルCT***%加速", "スキルクールタイム***%加速", "BSCT***%加速"],
    "BSCT進行": ["スキルCT***%進行"],
    "HACT加速": ["ヒートアクションCT***%加速"],
    "ダメージカット": ["ダメージカット"],
    "ダメージ増加": ["ダメージ増加"],
    "回復固定ダメージ強化": ["回復固定ダメージ****%強化"],
    "ダメージ無効化": ["被ダメージを***無効化"],
    "ヒートゲージ上昇": ["ヒートゲージ上昇量***上昇"],
    "不死": ["不死"],
    "会心威力上昇": ["会心時の攻撃力***上昇", "会心威力***上昇"],
    "会心率上昇": ["会心率***%上昇", "会心率上昇"],
    "体力上昇": ["体力***上昇"],
    "再起効果強化": ["再起***強化"],
    "命中率上昇": ["命中率***上昇", "命中率上昇"],
    "回復": ["***%回復"],
    "回避率上昇": ["回避率***上昇", "回避率上昇"],
    "攻撃力上昇": ["攻撃力***上昇", "攻撃力上昇"],
    "敵BSCTダウン": ["スキルCT***%減速"],
    "敵ヒートゲージ増加": ["HACTの消費ゲージを***増加"],
    "会心率減少": ["会心率***%減少", "会心率減少"],
    "敵回避率ダウン": ["敵の回避率を***%減少", "回避率を***%減少"],
    "敵攻撃ダウン": ["敵全体の攻撃力を***%減少", "敵の攻撃力を***秒間-***%減少", "敵の攻撃力を***秒間***%減少", "攻撃力を***%減少"],
    "敵速度減少": ["敵の速度を***秒間-***%減少", "速度を***%減少"],
    "敵防御ダウン": ["敵全体の防御力を***%減少", "敵の防御力を***秒間-***%減少", "敵の防御力を***秒間***%減少", "防御力を***%減少"],
    "特殊効果付与": ["秒間の泥酔", "秒間の睡眠", "特殊効果付与"],
    "特殊効果確率上昇": ["特殊効果の成功確率を***%上昇", "暗闇が成功する確率を***%上昇", "睡眠が成功する確率を***%上昇"],
    "状態異常付与": ["秒間の魅了付与", "秒間の封印付与", "秒間の混乱付与", "秒間の麻痺付与", "出血付与", "骨折付与", "打撲付与", "回復不可付与", "状態異常付与"],
    "状態異常確率上昇": ["与状態異常成功確率を***%上昇", "全状態異常が成功する確率***%上昇", "出血が成功する確率を***%上昇", "封印が成功する確率を***%上昇", "打撲が成功する確率を***%上昇", "拘束が成功する確率を***%上昇", "混乱が成功する確率を***%上昇", "麻痺が成功する確率を***%上昇"],
    "被特殊効果確率低減": ["特殊効果になる確率を***%減少", "被特殊効果確率を***%減少"],
    "被状態異常確率低減": ["状態異常になる確率を***%減少", "被状態異常確率低減", "出血状態になる確率を***%減少", "回復不可状態になる確率を***%減少", "封印状態になる確率を***%減少", "打撲状態になる確率を***%減少", "混乱状態になる確率を***%減少", "麻痺状態になる確率を***%減少"],
    "資金獲得量上昇": ["資金獲得量が***%上昇", "資金獲得量***%上昇"],
    "速度上昇": ["速度を***%上昇", "速度***%上昇"],
    "連打カット": ["複数回攻撃のダメージが", "与えるダメージが***%減少", "連打カット"],
    "連打増幅": ["複数回攻撃のダメージが", "与えるダメージが***%上昇", "連打増幅"],
    "防御力上昇": ["防御力を***%上昇", "防御力***%上昇", "防御力を***上昇"],
    "BS後退低減": ["BSCT後退を***%低減", "後退を***%低減"],
}
RULES: dict[str, list[re.Pattern]] = {cat: _compile_patterns(pats) for cat, pats in RAW_RULES.items()}


def infer_categories_from_text(text: str) -> set[str]:
    if text is None:
        return set()
    t = str(text)
    hits: set[str] = set()
    for cat, regs in RULES.items():
        if any(r.search(t) for r in regs):
            hits.add(cat)
    return hits


def infer_categories_for_ability_cell(ability_cell: str) -> set[str]:
    if ability_cell is None:
        return set()
    s = str(ability_cell).strip()
    if not s:
        return set()

    parts = [p.strip() for p in ABILITY_SPLIT_RE.split(s) if p.strip()]
    cats: set[str] = set()
    for part in parts:
        cats |= infer_categories_from_text(part)
    return cats


def add_ability_category_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    def _to_str(cats: set[str]) -> str | None:
        if not cats:
            return None
        return " / ".join(sorted(cats))

    out["アビリティカテゴリ"] = out["アビリティ"].apply(lambda x: _to_str(infer_categories_for_ability_cell(x)))
    return out


# =========================
# 装備番号付与（non_check_df用）
# =========================
def add_equipment_no_for_non_check(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["装備種類"] = out["装備種類"].astype(str).str.strip()
    out["レアリティ"] = out["レアリティ"].astype(str).str.strip().str.upper()

    out["_type_code"] = out["装備種類"].map(TYPE_CODE)
    out["_rarity_code"] = out["レアリティ"].map(RARITY_CODE)

    if out["_type_code"].isna().any():
        bad = out.loc[out["_type_code"].isna(), "装備種類"].unique().tolist()
        raise ValueError(f"装備種類のマッピングに失敗: {bad}")
    if out["_rarity_code"].isna().any():
        bad = out.loc[out["_rarity_code"].isna(), "レアリティ"].unique().tolist()
        raise ValueError(f"レアリティのマッピングに失敗: {bad}")

    out["_row_order"] = range(len(out))
    out = out.sort_values("_row_order")
    out["_idx"] = out.groupby(["装備種類", "レアリティ"], sort=False).cumcount().add(1)

    out["装備番号"] = out.apply(
        lambda r: f'{int(r["_type_code"])}_{int(r["_rarity_code"])}_1_{int(r["_idx"]):03d}',
        axis=1,
    )
    return out.drop(columns=["_type_code", "_rarity_code", "_idx", "_row_order"])


# =========================
# Google Sheets write
# =========================
def load_credentials_and_key() -> tuple[dict, str]:
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

    if not spreadsheet_key:
        raise RuntimeError("SPREADSHEET_KEY_NAME が見つかりません (.env か Secrets を確認してください)")

    return creds_info, spreadsheet_key


def write_df_to_sheet(df: pd.DataFrame, spreadsheet_key: str, creds_info: dict, sheet_name: str) -> None:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(spreadsheet_key)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(
            title=sheet_name,
            rows=str(max(1000, len(df) + 10)),
            cols=str(max(26, len(df.columns) + 5)),
        )

    def to_jsonable(v):
        if pd.isna(v):
            return ""
        if isinstance(v, np.generic):   # np.int64 等を python int/float に
            return v.item()
        if hasattr(v, "to_pydatetime"):
            return v.to_pydatetime().isoformat()
        return v

    values = [df.columns.tolist()]
    for row in df.itertuples(index=False, name=None):
        values.append([to_jsonable(v) for v in row])

    ws.clear()
    # ★古いgspread対応：位置引数で渡す
    ws.update("A1", values, value_input_option="USER_ENTERED")


# =========================
# main（デフォルトでDB+Sheet両方に書く）
# =========================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build non_check_df and write to SQLite + Google Sheets (default)."
    )
    parser.add_argument("--static-dir", default="static", help="画像ディレクトリ (default: static)")
    parser.add_argument("--no-write-db", action="store_true", help="DBへの書き込みを無効化")
    parser.add_argument("--no-write-sheet", action="store_true", help="シートへの書き込みを無効化")

    # staying_check_equipment_list を使わず明示指定したい場合
    parser.add_argument("--sheet-name", default=None, help="書き込み先シート名（未指定なら staying_check_equipment_list から解決）")
    parser.add_argument("--table-name", default=None, help="書き込み先テーブル名（未指定なら staying_check_equipment_list から解決）")

    # 参照自動探索に失敗した時の任意override
    parser.add_argument("--ref-weapon", default=None, help="武器参照画像パス（任意）")
    parser.add_argument("--ref-armor", default=None, help="防具参照画像パス（任意）")
    parser.add_argument("--ref-accessory", default=None, help="装飾参照画像パス（任意）")

    args = parser.parse_args()

    write_db = not args.no_write_db
    write_sheet = not args.no_write_sheet
    if not (write_db or write_sheet):
        raise SystemExit("no-write-db と no-write-sheet の両方が指定されているため何もしません。")

    static_dir = Path(args.static_dir)
    engine = create_engine(DB_URL)

    # 1) non_check候補
    non_check_df = build_non_check_candidates_df(engine)

    # 2) 装備種類付与
    if args.ref_weapon and args.ref_armor and args.ref_accessory:
        ref_paths = {"武器": Path(args.ref_weapon), "防具": Path(args.ref_armor), "装飾": Path(args.ref_accessory)}
    else:
        ref_paths = find_reference_images(engine, static_dir)

    refs = build_reference_icons(ref_paths)
    non_check_df = add_equip_type_column(non_check_df, static_dir=static_dir, refs=refs)

    # 3) アビリティカテゴリ付与
    non_check_df = add_ability_category_column(non_check_df)

    # 4) 装備番号付与
    non_check_df = add_equipment_no_for_non_check(non_check_df)

    # 5) NULL許容整数（0とNULLを区別）
    non_check_df = enforce_nullable_int_stats(non_check_df)

    # 6) 列順
    non_check_df = reorder_columns_for_output(non_check_df)

    # 7) 書き込み先解決
    sheet_name = args.sheet_name
    table_name = args.table_name
    if sheet_name is None or table_name is None:
        default_sheet, default_table = resolve_non_check_sheet_and_table(engine)
        sheet_name = sheet_name or default_sheet
        table_name = table_name or default_table

    # 8) DBへ書き込み
    if write_db:
        upsert_non_check_to_sqlite(engine, non_check_df, table_name=table_name)
        print(f"[DB] wrote table='{table_name}' rows={len(non_check_df)} (upsert by 装備名+レアリティ)")

    # 9) Sheetへ書き込み
    if write_sheet:
        creds_info, spreadsheet_key = load_credentials_and_key()
        write_df_to_sheet(non_check_df, spreadsheet_key=spreadsheet_key, creds_info=creds_info, sheet_name=sheet_name)
        print(f"[Sheet] wrote spreadsheet='{spreadsheet_key}' sheet='{sheet_name}' rows={len(non_check_df)}")

    print("Reference images:", {k: str(v) for k, v in ref_paths.items()})
    print("装備種類 counts:\n", non_check_df["装備種類"].value_counts(dropna=False))
    print("アビリティカテゴリ null:", int(non_check_df["アビリティカテゴリ"].isna().sum()))


if __name__ == "__main__":
    main()
