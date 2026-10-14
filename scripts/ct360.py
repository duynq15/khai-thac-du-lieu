"""Parse cantho360 TTPVHCC list -> phone/email for CT communes lacking them."""
import sys, json, re, glob, html, collections, unicodedata
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
raw = open(sys.argv[1], encoding="utf-8").read()
t = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
t = re.sub(r"[ \t\xa0]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t)
N = lambda s: unicodedata.normalize("NFC", s).lower().strip()
parts = re.split(r"\n\s*(\d+)\.\s*Trung tâm phục vụ hành chính công\s+", t)
ent = []
for i in range(1, len(parts) - 1, 2):
    blk = parts[i + 1]
    ten = blk.split("\n")[0].strip()
    dt = re.search(r"Điện thoại:\s*([0-9][0-9. ]{8,14}[0-9])", blk)
    em = re.search(r"Email:\s*([\w.+-]+@[\w.-]+\.vn)", blk)
    dc = re.search(r"Địa chỉ:\s*([^\n]+)", blk)
    ent.append(dict(stt=parts[i], ten=ten, dt=dt and dt.group(1).strip(), em=em and em.group(1),
                    td=re.sub(r"\s+", " ", blk[:blk.find("Email") + 60 if em else 300]).strip()))
ent=[e for e in ent if e["dt"] or e["em"]]; seen=set(); ent=[e for e in ent if not ((e["stt"],e["ten"]) in seen or seen.add((e["stt"],e["ten"])))]
for e in ent:
    if e["dt"] and len(re.sub(r"\D","",e["dt"])) != (11 if e["dt"].startswith("02") else 10): print("bỏ sđt sai độ dài", e["ten"], e["dt"]); e["dt"]=None
ALIAS={"phường mỹ qưới":"phường mỹ quới","xã thạnh qưới":"xã thạnh quới","xã hòa lựu":"xã hỏa lựu"}
print("entries", len(ent))
dem = collections.Counter(e["dt"] for e in ent if e["dt"])
d = json.load(open(sorted(glob.glob(G + "/du_lieu/ban_giao/ban_giao_*.json"))[-1], encoding="utf-8"))
ct = {N(u["ten"]): u for u in d["don_vi"] if u["tinh_ma"] == "92"}
dong, khong = [], []
for e in ent:
    u = ct.get(ALIAS.get(N(e["ten"]), N(e["ten"])))
    if not u: khong.append(e["ten"]); continue
    tr = {}
    if e["dt"] and dem[e["dt"]] == 1 and u["truong"]["dien_thoai"]["gia_tri"] is None: tr["dien_thoai"] = e["dt"]
    if e["em"] and u["truong"]["email"]["gia_tri"] is None: tr["email"] = e["em"]
    if tr:
        dong.append({"ten_xa": u["ten"], "truong": tr,
                     "trich_doan": f"{e['stt']}. Trung tâm phục vụ hành chính công {e['ten']} {e['td']}"[:400]})
print("không khớp", khong); print("trùng sđt", [k for k, v in dem.items() if v > 1])
print("dòng", len(dong), collections.Counter(k for r in dong for k in r["truong"]))
for r in dong[:4]: print(r)
json.dump(dong, open(G + "/du_lieu/tam_kt/ct360_dong.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
