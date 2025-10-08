from scraping_equipment import init_db, get_equipment_tables
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

# ===== DB挿入 =====
def insert_to_db(equips):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for eq in equips:
        cur.execute("""
            INSERT INTO eqipment_img_scraping
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

# ===== DBに登録済み番号を取得 =====
def get_existing_numbers():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT URL_Number FROM eqipment_img_scraping")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

# ===== テーブル取得 =====
def get_tables(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    return soup.find_all("table")

# ===== テーブルフィルタ =====
def filter_tables_by_string(tables, keyword: str):
    matched = []
    for table in tables:
        if keyword in table.get_text():
            matched.append(table)
    return matched

# ===== ステータス値解析 =====
def parse_stat_value(text: str):
    m = re.match(r"(体力|攻撃力|防御力|会心率|回避率|命中率)\+([\d.]+)(%)?", text)
    if m:
        key = m.group(1)
        val = float(m.group(2)) if "." in m.group(2) else int(m.group(2))
        return key, val
    return None, None

# ===== 画像DL =====
def download_image(img_url: str, filename: str):
    resp = requests.get(img_url, timeout=30)
    resp.raise_for_status()
    save_path = os.path.join(IMG_DIR, filename)
    with open(save_path, "wb") as f:
        f.write(resp.content)
    return save_path

# ===== 平均色算出 =====
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

# ===== レアリティ推定 =====
def classify_by_reference(mean_color, num):
    distances = {
        rank: np.linalg.norm(np.array(mean_color) - np.array(ref))
        for rank, ref in REFERENCE_COLORS.items()
    }
    predicted = min(distances, key=distances.get)

    if num < 2762:
        predicted = "SSR"
    elif num < 4594:
        if predicted == "UR":
            predicted = "KSR"
    return predicted

# ===== 装備情報パース =====
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
                tmp_img_name = f"{safe_name}.png"
                img_path = download_image(img_url, tmp_img_name)
                mean_color = get_filtered_mean_color(img_path)
                rarety = classify_by_reference(mean_color, url_num)
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

# ===== メインループ =====
def main_loop():
    existing = set(get_existing_numbers())
    skip_nums = set()
    # for n in existing:
    #     skip_nums.update(range(n-2, n+2))

    for num in range(2872, 2880):
        # if num in skip_nums:
        #     print(f"skip {num}")
        #     continue
        time.sleep(0.5)
        url = f"https://ryu.sega-online.jp/news/{num}/"
        print(f"processing {num} -> {url}")

        try:
            all_tables = get_tables(url)
            equip_tables = filter_tables_by_string(all_tables, "装備名称")
            if not equip_tables:
                print(f"No equipment table found for {num}")
                continue

            equips = parse_equipment_tables(
                equip_tables,
                base_url=url,
                url_num=num,
                now_branch="main"  # ブランチ名は必要に応じ変更
            )

            if equips:
                insert_to_db(equips)
                print(f"Inserted {len(equips)} equips from {num}")

        except Exception as e:
            print(f"Error at {num}: {e}")


if __name__ == "__main__":
    main_loop()
