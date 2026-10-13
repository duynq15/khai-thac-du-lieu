"""Giao diện dòng lệnh của bộ khai thác."""

from __future__ import annotations

import argparse
import sys

from . import cau_hinh
from . import http as http_mod
from .models import KetQua
from .proxy import PoolProxy, kiem_tra_hang_loat, tai_proxy
from .quy_trinh import NHOM_XA, chay_danh_muc, chay_nhom, chay_thon, chay_tinh
from .store import Kho
from .trich_xuat import ollama
from .xuat import xuat_excel, xuat_json


def _kho(args) -> Kho:
    return Kho(args.db)


def _ds_tu_db(kho: Kho, args) -> list[KetQua]:
    dong = kho.lay_ket_qua(
        don_vi_ma=getattr(args, "ma", None),
        nhom=getattr(args, "nhom", None),
        trang_thai=getattr(args, "trang_thai", None),
        moi_nhat=True,
    )
    return [_tu_dong(r) for r in dong]


def _tu_dong(r) -> KetQua:
    import json
    return KetQua(
        don_vi_ma=r["don_vi_ma"], don_vi_ten=r["don_vi_ten"], cap=r["cap"], nhom=r["nhom"],
        truong=r["truong"], gia_tri=r["gia_tri"], kieu=r["kieu"] or "van_ban",
        nguon_ma=r["nguon_ma"], nguon_ten=r["nguon_ten"], nguon_url=r["nguon_url"],
        nguon_muc=r["nguon_muc"], trich_doan=r["trich_doan"], diem_tin=r["diem_tin"] or 0,
        trang_thai=r["trang_thai"], ly_do_loi=r["ly_do_loi"],
        canh_bao=json.loads(r["canh_bao"]) if r["canh_bao"] else [],
        nam_du_lieu=r["nam_du_lieu"] if "nam_du_lieu" in r.keys() else None,
    )


def cmd_danh_muc(args) -> int:
    kho = _kho(args)
    ma_tinh = None if args.toan_quoc else ([x.strip() for x in args.tinh.split(",")] if args.tinh else None)
    kq = chay_danh_muc(kho, province_codes=ma_tinh)
    print(f"Đã nạp {kq['so_tinh']} tỉnh, {kq['so_xa']} xã/phường. Tổng trong kho: {kho.dem_don_vi()}.")

    if args.xuat:
        # Xuất danh mục ra JSON để bàn giao
        from .models import DonVi
        import json
        rows = kho.conn.execute("SELECT * FROM don_vi").fetchall()
        ds = [dict(r) for r in rows]
        from .store import DU_LIEU
        p = DU_LIEU / "ban_giao" / "danh_muc_dvhc.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(ds, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã xuất danh mục: {p}")
    kho.dong()
    return 0


def cmd_xa(args) -> int:
    kho = _kho(args)
    if not args.nhom:
        print("Cần --nhom. Các nhóm ở cấp xã:", ", ".join(cau_hinh.ds_nhom("xa")))
        return 2

    bo_qua = bool(cau_hinh.lay_ho_so("lo", "bo_qua_da_co", mac_dinh=True)) and not args.lam_lai
    so_moi_lo = int(cau_hinh.lay_ho_so("lo", "so_don_vi_moi_lo", mac_dinh=0) or 0)
    nghi = float(cau_hinh.lay_ho_so("lo", "nghi_giua_lo_giay", mac_dinh=0) or 0)

    pham_vi = "toàn quốc" if args.toan_quoc or (not args.ten and not args.ma and not args.tinh) else (
        args.ten or args.ma or args.tinh)
    print(f"Khai thác nhóm '{args.nhom}' · phạm vi: {pham_vi} · LLM={'bật' if args.dung_llm else 'tắt'}"
          + (" · chạy tiếp (bỏ đơn vị đã đạt)" if bo_qua else ""))

    chia = None
    if args.shard:
        try:
            k, n = args.shard.split("/")
            chia = (int(n), int(k))
        except ValueError:
            print("--shard phải dạng K/N, ví dụ 1/6")
            return 2

    ds_nhom = [x.strip() for x in args.nhom.split(",") if x.strip()]
    kq: list = []
    for nh in ds_nhom:
        kq += chay_nhom(kho, nh, ten=args.ten, ma=args.ma, tinh=args.tinh,
                        cap=args.cap, dung_llm=args.dung_llm, bo_qua_da_co=bo_qua,
                        gioi_han=args.gioi_han, so_moi_lo=so_moi_lo, nghi_giua_lo=nghi,
                        chia=chia, tinh_ma=args.tinh_ma)
    if args.xuat:
        if "json" in args.xuat:
            print("JSON:", xuat_json(kq))
        if "excel" in args.xuat:
            print("Excel:", xuat_excel(kq))
    print(f"Xong: {len(kq)} trường, {sum(1 for k in kq if k.trang_thai == 'dat')} đạt.")
    kho.dong()
    return 0


def cmd_xuat(args) -> int:
    kho = _kho(args)
    kq = _ds_tu_db(kho, args)
    if not kq:
        print("Không có kết quả nào khớp.")
        return 0
    if args.dinh_dang == "excel":
        print("Excel:", xuat_excel(kq))
    else:
        print("JSON:", xuat_json(kq))
    kho.dong()
    return 0


def cmd_thon(args) -> int:
    kho = _kho(args)
    if not args.ten and not args.ma and not args.tinh:
        print("Nên lọc bớt (--ma/--ten/--tinh). Không lọc sẽ crawl mọi xã trong kho.")
    print("Gom thôn/tổ dân phố từ trang riêng của xã (độ phủ tuỳ xã).")
    kq = chay_thon(kho, ten=args.ten, ma=args.ma, tinh=args.tinh,
                   so_trang=args.so_trang, mien=args.mien, tinh_ma=args.tinh_ma)
    print(f"Xong: {len(kq)} thôn/tổ dân phố cho {len({d.parent_ma for d in kq})} xã.")
    if kq and args.xuat:
        import json
        from .store import DU_LIEU
        p = DU_LIEU / "ban_giao" / "danh_muc_thon.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([d.to_dict() for d in kq], ensure_ascii=False, indent=2), encoding="utf-8")
        print("JSON:", p)
    kho.dong()
    return 0


def cmd_tien_do(args) -> int:
    import json
    import os
    from datetime import datetime

    from .store import DU_LIEU

    tep = sorted(DU_LIEU.glob("tien_trinh*.json"))
    if tep:
        print("== Tiến độ các luồng ==")
        for t in tep:
            tt = json.loads(t.read_text(encoding="utf-8"))
            print(f"  [{tt.get('shard') or '1/1':>3}] {tt.get('nhom')}: "
                  f"{tt.get('da_xong')}/{tt.get('tong')} · cuối: {tt.get('don_vi_cuoi')} "
                  f"· {tt.get('cap_nhat')}")
    else:
        print("Chưa có tệp tiến độ (chưa chạy lượt nào bằng bản có ghi tiến độ).")

    kho = _kho(args)
    print("\n== Trong kho ==")
    for r in kho.conn.execute("SELECT nhom, trang_thai, count(*) n FROM ket_qua "
                              "GROUP BY nhom, trang_thai ORDER BY nhom, n DESC"):
        print(f"  {r['nhom']:18} {r['trang_thai']:10} {r['n']}")
    da = kho.conn.execute(
        "SELECT count(DISTINCT don_vi_ma) FROM ket_qua WHERE don_vi_ma IN "
        "(SELECT ma FROM don_vi WHERE loai IN ('xa','phuong','dac_khu'))"
    ).fetchone()[0]
    print(f"\n  Xã/phường đã có kết quả: {da}/3321")
    kho.dong()
    return 0


def cmd_tinh(args) -> int:
    kho = _kho(args)
    nhom = None if args.nhom in (None, "all") else [x.strip() for x in args.nhom.split(",")]
    chia = None
    if args.shard:
        try:
            k, n = args.shard.split("/")
            chia = (int(n), int(k))
        except ValueError:
            print("--shard phải dạng K/N, ví dụ 1/4")
            return 2

    if args.khong_trinh_duyet:
        from .nguon import trinh_duyet

        trinh_duyet.tat()

    so_moi_lo = int(cau_hinh.lay_ho_so("lo", "so_don_vi_moi_lo", mac_dinh=0) or 0)
    nghi = float(cau_hinh.lay_ho_so("lo", "nghi_giua_lo_giay", mac_dinh=0) or 0)
    print(f"Cào tỉnh {args.ma}: nhóm {nhom or 'tất cả'} · "
          + (f"shard {args.shard} · " if chia else "")
          + ("chạy tiếp" if not args.lam_lai else "làm lại"))

    kq = chay_tinh(kho, args.ma, nhom=nhom, chia=chia, gioi_han=args.gioi_han,
                   dung_llm=args.dung_llm, bo_qua_da_co=not args.lam_lai,
                   so_moi_lo=so_moi_lo, nghi_giua_lo=nghi)
    if args.xuat:
        if "json" in args.xuat:
            print("JSON:", xuat_json(kq))
        if "excel" in args.xuat:
            print("Excel:", xuat_excel(kq))
    print(f"Xong: {len(kq)} trường, {sum(1 for k in kq if k.trang_thai == 'dat')} đạt.")
    kho.dong()
    return 0


def cmd_thong_ke(args) -> int:
    kho = _kho(args)
    c = kho.conn
    loc = ""
    p: list = []
    if getattr(args, "tinh_ma", None):
        loc = " AND d.tinh_ma = ?"
        p.append(args.tinh_ma)

    dong = c.execute(
        """
        SELECT d.tinh_ma, d.tinh_ten,
               COUNT(*) AS tong,
               COUNT(k.don_vi_ma) AS da_co
        FROM don_vi d
        LEFT JOIN (SELECT DISTINCT don_vi_ma FROM ket_qua) k ON k.don_vi_ma = d.ma
        WHERE d.loai IN ('xa','phuong','dac_khu')""" + loc + """
        GROUP BY d.tinh_ma, d.tinh_ten
        ORDER BY CAST(d.tinh_ma AS INTEGER)
        """,
        p,
    ).fetchall()

    print(f"{'Mã':>4} {'Tỉnh/Thành':32} {'Đã có':>6} {'Tổng':>6} {'%':>6}")
    tong_all = da_co_all = 0
    for r in dong:
        tong_all += r["tong"]
        da_co_all += r["da_co"]
        pc = (r["da_co"] / r["tong"] * 100) if r["tong"] else 0
        print(f"{r['tinh_ma']:>4} {r['tinh_ten'][:32]:32} {r['da_co']:>6} {r['tong']:>6} {pc:>5.0f}%")
    pc_all = (da_co_all / tong_all * 100) if tong_all else 0
    print("-" * 60)
    print(f"{'':>4} {'TỔNG':32} {da_co_all:>6} {tong_all:>6} {pc_all:>5.0f}%")

    print("\n== Theo nhóm ==")
    loc_nhom = ""
    pn: list = []
    if getattr(args, "tinh_ma", None):
        loc_nhom = " WHERE don_vi_ma IN (SELECT ma FROM don_vi WHERE tinh_ma = ?)"
        pn.append(args.tinh_ma)
    for r in c.execute(
        "SELECT nhom, COUNT(DISTINCT don_vi_ma) n, SUM(trang_thai='dat') dat "
        "FROM ket_qua" + loc_nhom + " GROUP BY nhom ORDER BY n DESC",
        pn,
    ):
        print(f"  {r['nhom']:18} {r['n']:>6} xã · {r['dat'] or 0:>6} trường đạt")
    kho.dong()
    return 0


def cmd_nongsan(args) -> int:
    kho = _kho(args)
    from .nguon.nongsan import nap

    res = nap(kho, tinh_ma=args.tinh_ma, gioi_han=args.gioi_han)
    print(f"Đã xét {res['xem']} sản phẩm · {res['san_pham']} gắn xã · {res['xã']} xã có OCOP (CHỜ DUYỆT)")
    kho.dong()
    return 0


def cmd_ocop_news(args) -> int:
    kho = _kho(args)
    from .nguon.ocop_news import nap_url

    tong = 0
    for url in args.url:
        r = nap_url(kho, url, tinh_ma=args.tinh_ma)
        print(f"  {r['san_pham']} SP / {r['xã']} xã · {url[:70]}")
        tong += r["xã"]
    print(f"Xong: {tong} xã có OCOP từ {len(args.url)} bài (chờ duyệt).")
    kho.dong()
    return 0


def cmd_ocop(args) -> int:
    kho = _kho(args)
    from .nguon.ocop import nap

    res = nap(kho, tinh_ma=args.tinh_ma, gioi_han=args.gioi_han,
              so_trang_moi_danh_muc=args.so_trang)
    print(f"Đã xét {res['xem']} sản phẩm · {res['san_pham']} gắn được xã · "
          f"{res['xã']} xã có OCOP (đưa vào CHỜ DUYỆT)")
    kho.dong()
    return 0


def cmd_do_mang(args) -> int:
    from .nguon.trinh_duyet import lay_mang, loc_ajax

    reqs = lay_mang(args.url)
    if not reqs:
        print("Không bắt được request (trang lỗi hoặc Playwright chưa cài).")
        return 1
    ajax = loc_ajax(reqs)
    print(f"Tổng request: {len(reqs)} · nghi AJAX/API: {len(ajax)}")
    for r in ajax[:args.so_luong]:
        print(f"  {r['method']:4} {r['type']:6} {r['url'][:100]}")
        if r.get("body"):
            print(f"        body: {r['body'][:220]}")
    return 0


def cmd_phap_ly(args) -> int:
    kho = _kho(args)
    from .nguon.phap_ly import nap

    res = nap(kho, args.tep, tinh_ma=getattr(args, "tinh_ma", None))
    print(f"Tệp: {res['tep']} · sha256:{res['sha256'][:16]}…")
    print(f"Bảng đọc được: {res['so_bang']} · ghi {res['so_ket_qua']} trường (đạt, nguồn văn bản pháp lý)")
    if res["khong_khop"]:
        print(f"Không khớp được {len(res['khong_khop'])} đơn vị:", res["khong_khop"][:8])
    kho.dong()
    return 0


def cmd_trang_thai(args) -> int:
    co = ollama.san_sang()
    print("Ollama:", "sẵn sàng" if co else "KHÔNG chạy (bỏ qua phần LLM)")
    if co:
        print("Model:", ", ".join(ollama.ds_model()) or "(chưa có model nào)")

    from .nguon.tim_kiem import khoa_brave, tim

    k = khoa_brave()
    print("Brave Search API:", "đã có khoá" if k else "CHƯA có khoá (sẽ scrape DDG/Bing)")
    if k:
        try:
            r = tim("Xã Đông Anh Hà Nội giới thiệu")
            print(f"  thử tìm kiếm: {len(r)} kết quả", [x['muc'] for x in r[:3]])
        except Exception as e:
            print("  thử tìm kiếm lỗi:", e)
    return 0


def cmd_proxy(args) -> int:
    if args.tai:
        n = tai_proxy()
        print(f"Đã tải {n} proxy công khai vào du_lieu/proxy.txt.")
    if args.kiem_tra:
        print(f"Đang kiểm tra {args.kiem_tra} proxy (song song)...")
        song, thu = kiem_tra_hang_loat(args.kiem_tra)
        print(f"Proxy sống: {song}/{thu}. Đã giữ lại danh sách sống trong du_lieu/proxy.txt.")
    if args.xem or not (args.tai or args.kiem_tra):
        pool = PoolProxy()
        print(f"Pool hiện có {len(pool)} proxy.")
        if len(pool):
            print("Kiểm tra nhanh 5 cái đầu...")
            ds = pool.chon_cho_kiem_tra(5)
            from .proxy import kiem_tra
            for p in ds:
                print("  ", "SỐNG" if kiem_tra(p) else "chết", p)
    return 0


def tao_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="khai-thac", description="Khai thác dữ liệu Xã Phường Việt Nam")
    p.add_argument("--db", default=None, help="Đường dẫn SQLite (mặc định: du_lieu/khai_thac.sqlite)")
    sub = p.add_subparsers(dest="lenh", required=True)

    d = sub.add_parser("danh-muc", help="Nạp danh mục tỉnh/xã từ nguồn mở")
    d.add_argument("--toan-quoc", action="store_true")
    d.add_argument("--tinh", help="Mã tỉnh, cách nhau dấu phẩy (vd 01,02)")
    d.add_argument("--xuat", action="store_true", help="Xuất JSON danh mục")
    d.add_argument("--dung-proxy", dest="dung_proxy", action="store_true",
                   help="Xoay proxy từ du_lieu/proxy.txt")
    d.add_argument("--nhanh", action="store_true", help="Giảm độ trễ ngẫu nhiên (chỉ khi phát triển)")
    d.set_defaults(fn=cmd_danh_muc)

    x = sub.add_parser("xa", help="Khai thác dữ liệu một/nhiều xã theo nhóm")
    x.add_argument("--ten", help="Tên đơn vị (khớp một phần)")
    x.add_argument("--ma", help="Mã đơn vị")
    x.add_argument("--tinh", help="Lọc theo tên tỉnh")
    x.add_argument("--tinh-ma", dest="tinh_ma", help="Lọc theo mã tỉnh (vd 01 = Hà Nội)")
    x.add_argument("--cap", default="xa", choices=["xa", "tinh", "thon"])
    x.add_argument("--nhom", required=True, help="Nhóm dữ liệu, vd thong_tin_chung")
    x.add_argument("--toan-quoc", action="store_true", help="Chạy mọi xã/phường trong kho")
    x.add_argument("--gioi-han", type=int, default=None, help="Chỉ chạy N đơn vị đầu (chạy thử)")
    x.add_argument("--lam-lai", action="store_true", help="Bỏ qua trạng thái đã đạt, làm lại từ đầu")
    x.add_argument("--shard", help="Chia việc cho nhiều tiến trình, dạng K/N (vd 1/6)")
    x.add_argument("--dung-llm", dest="dung_llm", action="store_true", default=True)
    x.add_argument("--khong-llm", dest="dung_llm", action="store_false")
    x.add_argument("--xuat", nargs="*", default=None, help="json excel")
    x.add_argument("--dung-proxy", dest="dung_proxy", action="store_true",
                   help="Xoay proxy từ du_lieu/proxy.txt")
    x.add_argument("--nhanh", action="store_true", help="Giảm độ trễ ngẫu nhiên (chỉ khi phát triển)")
    x.set_defaults(fn=cmd_xa)

    o = sub.add_parser("xuat", help="Xuất kết quả đã lưu")
    o.add_argument("--dinh-dang", choices=["json", "excel"], default="excel")
    o.add_argument("--ma", help="Lọc theo mã đơn vị")
    o.add_argument("--nhom", help="Lọc theo nhóm")
    o.add_argument("--trang-thai", dest="trang_thai", help="Lọc theo trạng thái")
    o.set_defaults(fn=cmd_xuat)

    t = sub.add_parser("trang-thai", help="Kiểm tra LLM/Ollama")
    t.set_defaults(fn=cmd_trang_thai)

    ti = sub.add_parser("tinh", help="Cào toàn bộ nhóm cho mọi xã của một tỉnh")
    ti.add_argument("--ma", required=True, help="Mã tỉnh (vd 01 = Hà Nội)")
    ti.add_argument("--nhom", default="all", help="Danh sách nhóm, cách nhau dấu phẩy (mặc định all)")
    ti.add_argument("--shard", help="Chia việc cho nhiều tiến trình, dạng K/N")
    ti.add_argument("--gioi-han", type=int, default=None, help="Chỉ chạy N xã đầu (chạy thử)")
    ti.add_argument("--lam-lai", action="store_true", help="Không bỏ qua đơn vị đã đạt")
    ti.add_argument("--dung-llm", dest="dung_llm", action="store_true", default=True)
    ti.add_argument("--khong-llm", dest="dung_llm", action="store_false")
    ti.add_argument("--khong-trinh-duyet", action="store_true",
                    help="Không mở Chrome (pha LLM: chỉ cache + HTTP tĩnh, tránh treo)")
    ti.add_argument("--xuat", nargs="*", default=None, help="json excel")
    ti.add_argument("--dung-proxy", dest="dung_proxy", action="store_true")
    ti.add_argument("--nhanh", action="store_true", help="Giảm độ trễ ngẫu nhiên (chỉ khi phát triển)")
    ti.set_defaults(fn=cmd_tinh)

    td = sub.add_parser("tien-do", help="Xem tiến độ lượt khai thác đang chạy")
    td.set_defaults(fn=cmd_tien_do)

    tk = sub.add_parser("thong-ke", help="Thống kê đã khai thác theo tỉnh/thành")
    tk.add_argument("--tinh-ma", dest="tinh_ma", help="Chỉ xem một tỉnh (vd 31)")
    tk.set_defaults(fn=cmd_thong_ke)

    th = sub.add_parser("thon", help="Gom thôn/tổ dân phố từ trang riêng của xã")
    th.add_argument("--ten", help="Tên xã (khớp một phần)")
    th.add_argument("--ma", help="Mã xã")
    th.add_argument("--tinh", help="Lọc theo tên tỉnh")
    th.add_argument("--tinh-ma", dest="tinh_ma", help="Lọc theo mã tỉnh (vd 01 = Hà Nội)")
    th.add_argument("--so-trang", type=int, default=3, help="Số trang mỗi xã tải để dò (mặc định 3)")
    th.add_argument("--mien", help="Tên miền trang xã (bỏ qua bước dò tìm kiếm)")
    th.add_argument("--xuat", action="store_true", help="Xuất JSON danh mục thôn")
    th.add_argument("--dung-proxy", dest="dung_proxy", action="store_true",
                    help="Xoay proxy từ du_lieu/proxy.txt")
    th.add_argument("--nhanh", action="store_true", help="Giảm độ trễ ngẫu nhiên (chỉ khi phát triển)")
    th.set_defaults(fn=cmd_thon)

    px = sub.add_parser("proxy", help="Tải và kiểm tra pool proxy")
    px.add_argument("--tai", action="store_true", help="Tải proxy công khai từ các nguồn")
    px.add_argument("--kiem-tra", type=int, default=0, metavar="N", help="Kiểm tra N proxy còn sống")
    px.add_argument("--xem", action="store_true", help="Xem trạng thái pool")
    px.set_defaults(fn=cmd_proxy)

    cs = sub.add_parser("chuyen-sau", help="Nạp dữ liệu chuyên sâu chính thống theo tỉnh")
    cs.add_argument("--tinh-ma", dest="tinh_ma", default="31", help="Mã tỉnh (mặc định 31 = Hải Phòng)")
    cs.set_defaults(fn=cmd_chuyen_sau)

    pl = sub.add_parser("phap-ly", help="Bóc dữ liệu từ văn bản pháp lý PDF/Excel (Đề án/Nghị quyết)")
    pl.add_argument("--tep", required=True, help="Đường dẫn PDF hoặc Excel")
    pl.add_argument("--tinh-ma", dest="tinh_ma", help="Giới hạn khớp đơn vị theo mã tỉnh")
    pl.set_defaults(fn=cmd_phap_ly)

    dm = sub.add_parser("do-mang", help="Dò request AJAX/API của một trang (SPA)")
    dm.add_argument("--url", required=True)
    dm.add_argument("--so-luong", type=int, default=40)
    dm.set_defaults(fn=cmd_do_mang)

    oc = sub.add_parser("ocop", help="Cào danh bạ OCOP Quốc gia (ocop.gov.vn)")
    oc.add_argument("--tinh-ma", dest="tinh_ma", help="Giới hạn khớp theo mã tỉnh")
    oc.add_argument("--gioi-han", type=int, default=None, help="Chỉ xét N sản phẩm (chạy thử)")
    oc.add_argument("--so-trang", type=int, default=15, help="Số trang mỗi danh mục (mặc định 15)")
    oc.set_defaults(fn=cmd_ocop)

    ns = sub.add_parser("nongsan", help="Cào Sàn nông sản Hải Phòng (có địa chỉ theo xã)")
    ns.add_argument("--tinh-ma", dest="tinh_ma", default="31")
    ns.add_argument("--gioi-han", type=int, default=None, help="Chỉ xét N sản phẩm (chạy thử)")
    ns.set_defaults(fn=cmd_nongsan)

    on = sub.add_parser("ocop-news", help="Bóc OCOP từ bài công bố (nhiều địa phương)")
    on.add_argument("--tinh-ma", dest="tinh_ma", help="Mã tỉnh để khớp xã")
    on.add_argument("--url", nargs="+", required=True, help="Một hoặc nhiều URL bài công bố")
    on.set_defaults(fn=cmd_ocop_news)
    return p


def cmd_chuyen_sau(args) -> int:
    kho = _kho(args)
    from .nguon.chuyen_sau import nap_du_lieu_chuyen_sau
    tinh_ma = getattr(args, "tinh_ma", "31") or "31"
    print(f"Đang nạp dữ liệu đề xuất biên tập (chờ duyệt) cho tỉnh {tinh_ma}...")
    res = nap_du_lieu_chuyen_sau(kho, ma_tinh=tinh_ma)
    print(f"Hoàn tất: Đã nạp {res.get('so_truong_de_xuat', 0)} trường đề xuất (trạng thái: chờ duyệt) cho {res['so_don_vi']} đơn vị.")
    kho.dong()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = tao_parser().parse_args(argv)

    # Độ trễ: --nhanh (phát triển) > hồ sơ chạy > mặc định 1.0
    if getattr(args, "nhanh", False):
        http_mod.dat_he_so_jitter(0.15)
        print("Chế độ nhanh: giảm độ trễ (chỉ dùng khi phát triển).")
    else:
        http_mod.dat_he_so_jitter(float(cau_hinh.lay_ho_so("mang", "he_so_jitter", mac_dinh=1.0) or 1.0))

    # Mô hình LLM theo hồ sơ chạy
    if cau_hinh.lay_ho_so("llm", "dung", mac_dinh=True) is False:
        args.dung_llm = False if hasattr(args, "dung_llm") else None

    # Proxy: --dung-proxy hoặc bật sẵn trong hồ sơ chạy
    dung_proxy = getattr(args, "dung_proxy", False) or bool(
        cau_hinh.lay_ho_so("mang", "dung_proxy", mac_dinh=False))
    if dung_proxy and getattr(args, "fn", None) is not cmd_proxy:
        pool = PoolProxy()
        if len(pool):
            http_mod.bat_proxy(pool)
            print(f"Đã bật proxy: {len(pool)} proxy, {pool.con_song()} còn sống.")
        else:
            print("Chưa có proxy. Chạy: khai-thac proxy --tai --kiem-tra 80")

    # Tự động chuyển proxy khi bị chặn
    http_mod.bat_tu_dong_proxy(bool(cau_hinh.lay_ho_so("mang", "proxy_tu_dong", mac_dinh=True)))

    try:
        return args.fn(args)
    finally:
        from .nguon import trinh_duyet

        trinh_duyet.dong_browser()


if __name__ == "__main__":
    sys.exit(main())
