"""Bản ghi govvn đã 'loi' mà vẫn được xuất (trích dẫn nghi bịa, email sai) → 'bo' (DB đã sao lưu ở bước trước)."""
import sys
G = str(__import__("pathlib").Path(__file__).resolve().parents[1])
sys.path.insert(0, G)
from khai_thac.store import Kho
k = Kho(G + "/du_lieu/khai_thac.sqlite")
ids = [(r["ly_do_loi"], r["id"]) for r in k.lay_ket_qua(moi_nhat=True)
       if r["nguon_ma"] == "govvn" and r["trang_thai"] == "loi" and r["gia_tri"]]
k.conn.executemany("UPDATE ket_qua SET trang_thai='bo', ly_do_loi='Rác cổng xã: ' || ? WHERE id=?", ids)
k.conn.commit(); print("bo", len(ids))
