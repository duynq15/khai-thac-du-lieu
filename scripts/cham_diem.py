import json, glob, collections
G = str(__import__("pathlib").Path(__file__).resolve().parents[1]) + "/du_lieu/ban_giao/"
d = json.load(open(sorted(glob.glob(G + "ban_giao_*.json"))[-1], encoding="utf-8"))
sch = {t["khoa"]: t for t in d["schema"]["xa"]}
nhom = collections.defaultdict(lambda: [0, 0])
bb = [0, 0]; co = dat = cung = chung = 0; tong = 0
for u in d["don_vi"]:
    for k, t in u["truong"].items():
        tong += 1; g = t["gia_tri"] is not None
        nhom[sch[k]["nhom"]][0] += 1; nhom[sch[k]["nhom"]][1] += g
        if sch[k].get("bat_buoc"): bb[0] += 1; bb[1] += g
        if g:
            co += 1; dat += t["trang_thai"] == "dat"
            chung += bool(t.get("trich_doan") or t["nguon"].get("url"))
            cung += t["nguon"]["muc"] in ("A", "B")
print("tong", tong, "co", co, f"{co/tong:.1%}", "bat_buoc", bb, f"{bb[1]/bb[0]:.1%}")
print("dat", f"{dat/co:.1%}", "A/B", f"{cung/co:.1%}", "co nguon", f"{chung/co:.1%}")
for n, (a, b) in sorted(nhom.items(), key=lambda x: -x[1][1] / x[1][0]): print(f"  {n:24} {b/a:5.0%}")
