import sqlite3

db_path = "equipment.db"

def rename_assets(rarity, old_name, new_name):
    """
    装備名=old_name かつ レアリティ=rarity の行について、
    画像名 / IMG_Path / IMG_URL の中の old_name を new_name に部分置換する
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE equipment_img_scraping
        SET 装備名   = REPLACE(装備名,   ?, ?),
            画像名   = REPLACE(画像名,   ?, ?),
            IMG_Path = REPLACE(IMG_Path, ?, ?),
            IMG_URL  = REPLACE(IMG_URL,  ?, ?)
        WHERE 装備名 = ? AND レアリティ = ?
          AND (
              画像名   LIKE '%' || ? || '%'
           OR IMG_Path LIKE '%' || ? || '%'
           OR IMG_URL  LIKE '%' || ? || '%'
          )
        """,
        (
            old_name, new_name,
            old_name, new_name,
            old_name, new_name,
            old_name, new_name,
            old_name, rarity,
            old_name, old_name, old_name
        )
    )

    conn.commit()
    updated = cur.rowcount
    conn.close()
    return updated

if __name__ == "__main__":
    n = rename_assets("KSR", "亜門のコート・極", "亜門のコート")
    print("updated rows:", n)
