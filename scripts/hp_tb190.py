"""Build nguon_tay/hp_tb190.json: hotline per HP commune from the list attached to TB 190/TB-UBND
(27/6/2025), only for communes with empty dien_thoai; drop numbers shared by several units."""
import re, json, glob, unicodedata, collections
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1]))
N = lambda s: re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).lower().replace("hoà", "hòa").replace("thuỷ", "thủy").strip()
emp = {N(u["ten"]): u for u in d["don_vi"] if u["tinh_ma"] == "31" and u["truong"]["dien_thoai"]["gia_tri"] is None}
emp_all = {N(u["ten"]) for u in d["don_vi"] if u["tinh_ma"] == "31"}
L = open(G + "/du_lieu/tam_kt/pdf/hp_raw.txt").read().splitlines()
starts = [i for i in range(len(L) - 1) if re.fullmatch(r"\d{1,3}", L[i].strip()) and L[i + 1].startswith("Trung tâm Phục vụ")]
PH = re.compile(r"(?:0|\+84)[\d.\s]{7,13}\d")
rows = []
for a, b in zip(starts, starts[1:] + [len(L)]):
    blk = " ".join(x.strip() for x in L[a:b])
    nb = N(blk)
    ten = max((t for t in emp_all if re.match(r"\d+ trung tâm phục vụ hành chính (?:công )?" + re.escape(t) + r"\b", nb)), key=len, default=None)
    if not ten: continue
    phones = [t for t in blk.split("Số: 190")[0].split() if re.fullmatch(r"0[\d.]{8,14}", t) and len(re.sub(r"\D", "", t)) in (10, 11)]
    rows.append((ten, phones, blk.split("Số: 190")[0].strip()))
rows = [r for r in rows if sum(x[0] == r[0] for x in rows) == 1 or N(r[0]) in N(r[2]).split(r[0], 1)[1]]  # duplicate header: keep block whose address names the commune
dem = collections.Counter(p for _, ps, _ in rows for p in ps)
dong = []
for ten, ps, blk in rows:
    ps = [p for p in ps if dem[p] == 1]
    if ten in emp and ps:
        dong.append({"ten_xa": emp[ten]["ten"], "truong": {"dien_thoai": ", ".join(ps)}, "trich_doan": blk})
print(len(rows), "rows;", len(dong), "fill;", "missing:", sorted(set(emp) - {r[0] for r in rows}))
json.dump({"ma": "hp_tb190", "tinh_ma": "31", "nam": 2025, "muc": "B",
           "ten": "Danh sách địa chỉ Trung tâm Phục vụ hành chính công cấp xã kèm Thông báo 190/TB-UBND ngày 27/6/2025 – UBND TP Hải Phòng",
           "url": "https://cdn.haiphong.gov.vn/gov-hpg/6801/tintuc/2025/7/danh-sach-cac-ttpvhcc-tren-dia-ban-thanh-pho-hai-phong-moi-.signed638867204145777002638881733463261203.pdf",
           "dong": dong}, open(G + "/du_lieu/nguon_tay/hp_tb190.json", "w"), ensure_ascii=False, indent=1)
for x in dong[:5]: print(x)
