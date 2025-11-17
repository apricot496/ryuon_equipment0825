import requests
from bs4 import BeautifulSoup
import urllib.parse
from PIL import Image
import numpy as np
from dotenv import load_dotenv
import re
import os
import time
import sqlite3

IMG_DIR = "static"
DB_PATH = "equipment.db"

REFERENCE_COLORS = {
    "SSR": (105, 160, 161),
    "KSR": (143, 156, 152),
    "UR":  (158, 155, 140),
}
os.makedirs(IMG_DIR, exist_ok=True)


# ===== DB関連 =====
def init_db():
    """テーブルが無ければ作成"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS equipment_img_scraping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            装備名 TEXT,
            レアリティ TEXT,
            画像名 TEXT,
            体力 REAL,
            攻撃力 REAL,
            防御力 REAL,
            会心率 REAL,
            回避率 REAL,
            命中率 REAL,
            アビリティ TEXT,
            新規フラグ INTEGER,
            URL_Number INTEGER,
            IMG_URL TEXT
        )
    """)
    conn.commit()
    conn.close()

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

def get_db_max_url():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT MAX(URL_Number) FROM equipment_img_scraping")
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else 0


# ===== HTMLスクレイピング =====
def get_equipment_tables(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    equipment_info_table_list = []
    for table in soup.find_all("table"):
        if table.find("th", class_="th30", string="装備名称"):
            equipment_info_table_list.append(table)
    return equipment_info_table_list

def parse_stat_value(text: str):
    m = re.match(r"(体力|攻撃力|防御力|会心率|回避率|命中率)\+([\d.]+)(%)?", text)
    if m:
        key = m.group(1)
        val = float(m.group(2)) if "." in m.group(2) else int(m.group(2))
        return key, val
    return None, None

def download_image(img_url: str, filename: str):
    resp = requests.get(img_url, timeout=30)
    resp.raise_for_status()
    save_path = os.path.join(IMG_DIR, filename)
    with open(save_path, "wb") as f:
        f.write(resp.content)
    return save_path

# ===== レアリティ判定 =====
def get_filtered_mean_color(img_path, threshold=40):
    image = Image.open(img_path).convert("RGB")
    roi = image.crop((92, 0, 160, 38))
    arr = np.array(roi).reshape(-1, 3)
    mask = np.all(arr >= threshold, axis=1)
    filtered = arr[mask]
    if len(filtered) == 0:
        mean_color = arr.mean(axis=0)
    else:
        mean_color = filtered.mean(axis=0)
    return tuple(map(int, mean_color))

def classify_by_reference(mean_color, num):
    # 色距離で推定
    distances = {
        rank: np.linalg.norm(np.array(mean_color) - np.array(ref))
        for rank, ref in REFERENCE_COLORS.items()
    }
    predicted = min(distances, key=distances.get)

    # 出現時期に応じて補正
    if num < 2762:
        # KSR, UR が存在しない → SSR固定
        predicted = "SSR"
    elif num < 4594:
        # UR が存在しない → URが出たらKSRに修正
        if predicted == "UR":
            predicted = "KSR"
    # 4594以降は補正不要（SSR/KSR/UR全部存在）

    return predicted



def parse_equipment_tables(equipment_info_table_list, base_url: str, url_num, now_branch):
    equips = []
    for table in equipment_info_table_list:
        for th in table.select("th.textCenter"):
            td = th.find_next("td")
            if not td:
                continue
            new_flag = 1 if th.find("strong", string="NEW!") else 0
            for strong in th.find_all("strong", string="NEW!"):
                strong.decompose()
            for br in th.find_all("br"):
                br.decompose()
            for span in th.find_all("span", class_="attentionMark"):
                span.decompose()
            name = th.get_text(strip=True)
            img_tag = th.find("img")
            img_url = urllib.parse.urljoin(base_url, img_tag["src"]) if img_tag else None
            img_name, rarety = None, None
            if img_url:
                safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
                # 仮に一度保存してレアリティ判定
                tmp_img_name = f"{safe_name}.png"
                img_path = download_image(img_url, tmp_img_name)
                mean_color = get_filtered_mean_color(img_path)
                rarety = classify_by_reference(mean_color, url_num)
                # レアリティをファイル名に組み込む
                img_name = f"{safe_name}_{rarety}.png"
                final_path = os.path.join(IMG_DIR, img_name)
                os.rename(img_path, final_path)

            stats = {}
            ability = None
            for li in td.select("li"):
                text = li.get_text(strip=True)
                key, val = parse_stat_value(text)
                if key:
                    stats[key] = val
                elif text.startswith("アビリティ"):
                    sub_ul = li.find("ul")
                    if sub_ul:
                        ability = sub_ul.get_text(strip=True)
                    else:
                        ability = text

            equips.append({
                "装備名": name,
                "レアリティ": rarety,
                "画像名": img_name,
                **stats,
                "アビリティ": ability,
                "新規フラグ": new_flag,
                "URL_Number": url_num,
                "IMG_URL": f"https://raw.githubusercontent.com/apricot496/ryuon_equipment0825/{now_branch}/static/{img_name}"
            })
    return equips


def get_news_max_url():
    """ニュース一覧ページから最大URL番号を取得"""
    url = "https://ryu.sega-online.jp/news/"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    max_id = 0
    for a in soup.select("ul.news__list a[href]"):
        m = re.search(r"/news/(\d+)/", a["href"])
        if m:
            val = int(m.group(1))
            max_id = max(max_id, val)

    if max_id == 0:
        raise RuntimeError("ニュース一覧から最大IDを取得できませんでした")
    return max_id


if __name__ == "__main__":
    init_db()
    load_dotenv()
    now_branch = os.getenv("NOW_BRANCH")
    print(now_branch)

    start = get_db_max_url() + 1
    if start <129:
        start = 129
    end = get_news_max_url()
    # 障害対応用（ローカル実行時コメントアウトを外す）
    # start = 5148
    # end = start+2
    print(f"スクレイピング範囲: {start} ～ {end}")
    for num in range(start, end + 1):
        url = f"https://ryu.sega-online.jp/news/{num}/"
        try:
            tables = get_equipment_tables(url)
        except Exception as e:
            print(f"エラー: {num} ({e})")
            time.sleep(1)
            continue
        if len(tables) > 0:
            equips = parse_equipment_tables(tables, url, num, now_branch)
            insert_to_db(equips)
            print(f"DB登録完了: {num}")
        else:
            insert_to_db([{"URL_Number": num}])
            print(f"空登録: {num}")
        time.sleep(0.5)
