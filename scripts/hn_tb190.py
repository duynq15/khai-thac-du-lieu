"""Build nguon_tay/hn_tb190.json: phone per HN commune from Phu luc I TB 190/TB-TTPVHCC,
only for communes with empty dien_thoai; drop numbers shared by several communes (central hotline)."""
import re, json, glob, unicodedata, collections
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1]))
N = lambda s: unicodedata.normalize("NFC", s).lower().replace("hoà", "hòa").strip()
bare = lambda t: t.split(" ", 1)[1] if t.split(" ", 1)[0] in ("Xã", "Phường") else t
emp = {N(bare(u["ten"])): u for u in d["don_vi"]
       if u["tinh_ma"] == "01" and u["truong"].get("dien_thoai", {}).get("gia_tri") is None}
rows = {}
for l in open(G + "/du_lieu/tam_kt/hn126.txt").read().splitlines():
    m = re.match(r"^\s*\d{1,3}\s{1,8}(\S.*?)\s{2,}.*?((?:0|\+84)[\d.\s]{8,14}\d)(\s*\(tạm thời\))?\s*$", l)
    if m: rows[N(m.group(1))] = (re.sub(r"\s", "", m.group(2)), re.sub(r"\s{2,}", "  ", l.strip()), m.group(1).strip())
dem = collections.Counter(p for p, _, _ in rows.values())
dong = [{"ten_xa": emp[k]["ten"], "truong": {"dien_thoai": p}, "trich_doan": td}
        for k, (p, td, _) in rows.items() if k in emp and dem[p] == 1]
json.dump({"ma": "hn_tb190", "tinh_ma": "01", "nam": 2025, "muc": "B",
           "ten": "Phụ lục I kèm Thông báo 190/TB-TTPVHCC ngày 30/6/2025 – Trung tâm Phục vụ hành chính công Hà Nội",
           "url": "https://sqhx-hanoi.mediacdn.vn/91579363132710912/2025/7/7/phu-luc-126-diem-phuc-vu-hanh-chinh-cong-thuoc-xa-va-cac-chi-nhanh-duong-day-nong-1751857119012548747852.pdf",
           "dong": dong}, open(G + "/du_lieu/nguon_tay/hn_tb190.json", "w"), ensure_ascii=False, indent=1)
print(len(dong), "shared:", {p: c for p, c in dem.items() if c > 1})
