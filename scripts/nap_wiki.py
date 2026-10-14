"""Pha 2: sao lưu DB rồi bóc gioi_thieu / nguồn gốc tên / diên cách từ bài Wikipedia đã cache
bằng QUY TẮC (không LLM), qua đúng bước kiểm trích dẫn của quy_trinh."""
import sys, json, shutil, time, collections
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from datetime import datetime
from khai_thac import cau_hinh, quy_trinh
from khai_thac.store import Kho
from khai_thac.models import Luot
quy_trinh._boc_llm_hang_loat = lambda *a, **k: {}   # chỉ quy tắc
db = G + "/du_lieu/khai_thac.sqlite"
shutil.copy2(db, G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_nap_wiki.sqlite")
k = Kho(db)
cache = json.load(open(G + "/du_lieu/tam_kt/wiki_cache.json"))
xa = {r["ma"]: r for t in ("01", "31", "46", "48", "79", "92") for r in k.tim_don_vi(tinh_ma=t, cap="xa")}
luot = Luot(ma=f"wiki-xa-{datetime.now():%Y%m%d-%H%M%S}", pham_vi="6tp", nhom_du_lieu="wiki",
            bat_dau=datetime.now().isoformat(timespec="seconds"))
LAY = {"gioi_thieu", "nguon_goc_ten_xa", "dien_cach_hanh_chinh"}
c = collections.Counter(); tong = 0
for ma, bai in cache.items():
    if not bai or ma not in xa:
        continue
    n = [{"nguon_ma": "wikipedia_vi", "nguon_ten": "Wikipedia tiếng Việt", "url": bai["url"],
          "muc": "C", "van_ban": bai["extract"]}]
    for nhom in cau_hinh.ds_nhom("xa"):
        khoa = {t["khoa"] for t in cau_hinh.ds_truong("xa", nhom)}
        if not khoa & LAY:
            continue
        kq = [r for r in quy_trinh.khai_thac_don_vi(xa[ma], nhom, nguons=n, bo_qua=khoa - LAY) if r.gia_tri is not None]
        tong += k.ghi_ket_qua(kq, luot.ma)
        for r in kq: c[(r.truong, r.trang_thai)] += 1
luot.ket_thuc = datetime.now().isoformat(timespec="seconds"); luot.so_ket_qua = tong
luot.nguon = ["wikipedia_vi"]; k.ghi_luot(luot)
for x, v in sorted(c.items()): print(v, x)
