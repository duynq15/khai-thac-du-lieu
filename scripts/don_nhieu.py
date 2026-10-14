"""Sao lưu DB rồi đánh dấu trang_thai='bo' (KHÔNG xoá) cho bản ghi govvn là rác:
giới thiệu bóc từ trang chủ, chủ tịch không phải họ tên, tiêu đề tin/thông báo."""
import sys, shutil, json, time, collections
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from khai_thac.store import Kho
from khai_thac.kiem_tra import la_tieu_de_tin
db = G + "/du_lieu/khai_thac.sqlite"
bk = G + f"/du_lieu/sao_luu/khai_thac_{time.strftime('%Y%m%d_%H%M%S')}_truoc_don_nhieu.sqlite"
shutil.copy2(db, bk); print("sao lưu", bk)
k = Kho(db)
sua = []; c = collections.Counter()
for id_, truong, gt, tt, url in k.conn.execute(
        "SELECT id, truong, gia_tri, trang_thai, nguon_url FROM ket_qua WHERE nguon_ma='govvn' AND trang_thai!='bo'"):
    try: v = json.loads(gt) if gt and gt[:1] in "[{\"" else gt
    except ValueError: v = gt
    if truong == "gioi_thieu" and "gioi-thieu" not in (url or ""): ly = "giới thiệu bóc từ trang chủ (danh sách tin)"
    elif truong == "chu_tich_ubnd" and tt == "loi": ly = "chủ tịch UBND không phải họ tên"
    elif gt and la_tieu_de_tin(v): ly = "tiêu đề tin/thông báo"
    else: continue
    sua.append(("Rác cổng xã: " + ly, id_)); c[(truong, ly)] += 1
k.conn.executemany("UPDATE ket_qua SET trang_thai='bo', ly_do_loi=? WHERE id=?", sua); k.conn.commit()
for x, n in c.most_common(): print(n, x)
print("tổng đánh dấu bo", len(sua))
