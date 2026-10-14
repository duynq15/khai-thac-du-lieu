"""Backup DB, then: (1) re-run kiem() on dien_cach_hanh_chinh / nguon_goc_ten_xa rows and mark
failures 'bo' (never delete); (2) tru_so values prefixed "Địa chỉ:" get a cleaned copy row, old row 'bo'."""
import sys, json, re, shutil, time
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from datetime import datetime
from khai_thac import cau_hinh
from khai_thac.kiem_tra import kiem
from khai_thac.store import Kho
from khai_thac.models import Luot
db = G + "/du_lieu/khai_thac.sqlite"
shutil.copy2(db, G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_don_rac.sqlite")
k = Kho(db); c = k.conn
cfg = {t["khoa"]: t for t in cau_hinh.ds_truong("xa", "lich_su_dia_danh")}
bo = 0
for tr in ("dien_cach_hanh_chinh", "nguon_goc_ten_xa"):
    for i, g in c.execute("SELECT id, gia_tri FROM ket_qua WHERE truong=? AND trang_thai IN ('dat','cho_duyet')", (tr,)).fetchall():
        try: v = json.loads(g)
        except Exception: v = g
        tt, _, ly_do, _ = kiem({"kiem_tra": ["cau_dien_giai"]}, v)
        if tt == "loi":
            c.execute("UPDATE ket_qua SET trang_thai='bo', ly_do_loi=? WHERE id=?", (ly_do, i)); bo += 1
luot = Luot(ma=f"don-tru-so-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="6tp", nhom_du_lieu="lien_he",
            bat_dau=datetime.now().isoformat(timespec="seconds"))
cols = [r[1] for r in c.execute("PRAGMA table_info(ket_qua)") if r[1] != "id"]
moi = 0
for r in c.execute("SELECT * FROM ket_qua WHERE truong='tru_so' AND trang_thai IN ('dat','cho_duyet')").fetchall():
    v = r["gia_tri"]
    if not isinstance(v, str) or not re.match(r"(?i)địa chỉ\s*:", v): continue
    sach = re.sub(r"(?i)^địa chỉ\s*:\s*", "", v).strip()
    d = dict(r); d["gia_tri"] = sach; d["luot_ma"] = luot.ma
    c.execute(f"INSERT INTO ket_qua ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [d[x] for x in cols])
    c.execute("UPDATE ket_qua SET trang_thai='bo', ly_do_loi='Thay bằng bản bỏ tiền tố \"Địa chỉ:\"' WHERE id=?", (r["id"],))
    moi += 1
c.commit()
luot.ket_thuc = datetime.now().isoformat(timespec="seconds"); luot.so_don_vi = moi; luot.so_ket_qua = moi
luot.nguon = ["don_rac"]; k.ghi_luot(luot)
print("bo", bo, "tru_so sach", moi)
