"""Turn rows that one-off scripts wrote straight into ket_qua into du_lieu/nguon_tay/<ma>.json,
so `khai-thac nap-tay` is the only write path. Read-only on the DB; prints per-file counts."""
import json, sqlite3, sys, collections
from pathlib import Path
G = Path(__file__).resolve().parents[1]
LUOT = {  # file stem → (direct-write runs, nguon_ma in those runs)
    "hp_tb233": (["lienhe-gio-20261013-204041"], "hp_tb233"),
    "cong_xa_lienhe": (["lienhe-gio-20261013-204041"], "cong_xa"),
    "hue_qd4010": (["gio-hue-20261013-204410"], "hue_qd4010"),
    "hcm_qd67_2017": (["gio-hcm-20261013-210635", "gio-hcm-20261013-214606"], "hcm_qd67_2017"),
    "bao_ds_chu_tich_2025": (["chutich-bao-20261013-204740"], "bao_ds_chu_tich_2025"),
    "tong_hop_danh_muc": (["diencach-tonghop-20261013-210259", "nguongocten-tonghop-20261013-210346",
                           "gioithieu-tonghop-20261013-185158"], "tong_hop_danh_muc"),
    "govvn_tru_so": (["don-tru-so-20261013-203422"], "govvn"),
}
c = sqlite3.connect(G / "du_lieu/khai_thac.sqlite"); c.row_factory = sqlite3.Row
for stem, (luot, nguon) in LUOT.items():
    p = G / "du_lieu/nguon_tay" / f"{stem}.json"
    if p.exists() and "--ghi-de" not in sys.argv:
        sys.exit(f"{p} đã có")
    rows = c.execute(f"SELECT k.*, d.tinh_ma FROM ket_qua k JOIN don_vi d ON d.ma = k.don_vi_ma WHERE luot_ma IN"
                     f" ({','.join('?' * len(luot))}) AND nguon_ma = ? AND trang_thai = 'dat' ORDER BY k.id",
                     (*luot, nguon)).fetchall()
    pho = lambda k: collections.Counter(r[k] for r in rows).most_common(1)[0][0]
    cfg = {"ma": stem, "ten": pho("nguon_ten"), "url": pho("nguon_url"), "muc": pho("nguon_muc"), "dong": []}
    for r in rows:
        gt = r["gia_tri"] if r["kieu"] in ("van_ban", "email", "so_dien_thoai", "url") else json.loads(r["gia_tri"])
        d = {"ten_xa": r["don_vi_ten"], "ma_xa": r["don_vi_ma"], "tinh_ma": r["tinh_ma"],
             "truong": {r["truong"]: gt}, "trich_doan": r["trich_doan"], "url": r["nguon_url"],
             "nguon_ten": r["nguon_ten"], "nam": r["nam_du_lieu"]}
        if json.loads(r["canh_bao"] or "[]"):
            d["canh_bao"] = json.loads(r["canh_bao"])
        assert r["nguon_muc"] == cfg["muc"], (stem, r["id"])
        cfg["dong"].append(d)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(stem, len(rows))
