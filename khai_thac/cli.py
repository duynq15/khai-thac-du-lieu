"""Giao diện dòng lệnh của bộ khai thác."""

from __future__ import annotations

import argparse
import sys

from . import cau_hinh
from . import http as http_mod
from .models import KetQua
from .proxy import PoolProxy, kiem_tra_hang_loat, tai_proxy
from .quy_trinh import chay_danh_muc, chay_thon, chay_tinh
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


def _chia(shard: str | None) -> tuple[int, int] | None:
    """'K/N' -> (N, K); sai dạng -> SystemExit."""
    if not shard:
        return None
    try:
        k, n = shard.split("/")
        return int(n), int(k)
    except ValueError:
        raise SystemExit("--shard phải dạng K/N, ví dụ 1/6") from None


def _chay(args, *, tinh_ma: str | None, nhom: list[str] | None) -> int:
    """Chung cho `xa` và `tinh`: một vòng khai thác (quy_trinh.chay_tinh) + xuất."""
    kho = _kho(args)
    if getattr(args, "khong_trinh_duyet", False):
        from .nguon import trinh_duyet

        trinh_duyet.tat()
    from . import quy_trinh

    quy_trinh.CHE_DO_LLM = ("xuat" if getattr(args, "xuat_nguon", False)
                            else "tep" if getattr(args, "llm_tu_tep", False) else "ollama")
    bo_qua = bool(cau_hinh.lay_ho_so("lo", "bo_qua_da_co", mac_dinh=True)) and not args.lam_lai
    pham_vi = getattr(args, "ma", None) if args.fn is cmd_xa else None
    print(f"Khai thác {pham_vi or getattr(args, 'ten', None) or (f'tỉnh {tinh_ma}' if tinh_ma else 'toàn quốc')}"
          f" · nhóm {nhom or 'tất cả'} · LLM={'bật' if args.dung_llm else 'tắt'}"
          + (f" · shard {args.shard}" if args.shard else "") + (" · chạy tiếp" if bo_qua else " · làm lại"))
    kq = chay_tinh(
        kho, tinh_ma, nhom=nhom, chia=_chia(args.shard), gioi_han=args.gioi_han,
        dung_llm=args.dung_llm, bo_qua_da_co=bo_qua,
        so_moi_lo=int(cau_hinh.lay_ho_so("lo", "so_don_vi_moi_lo", mac_dinh=0) or 0),
        nghi_giua_lo=float(cau_hinh.lay_ho_so("lo", "nghi_giua_lo_giay", mac_dinh=0) or 0),
        ma=pham_vi, ten=getattr(args, "ten", None), tinh_ten=getattr(args, "tinh", None),
        cap=getattr(args, "cap", "xa"),
    )
    for dd in args.xuat or []:
        print(dd.upper() + ":", {"json": xuat_json, "excel": xuat_excel}[dd](kq))
    print(f"Xong: {len(kq)} trường, {sum(1 for k in kq if k.trang_thai == 'dat')} đạt.")
    kho.dong()
    return 0


def cmd_xa(args) -> int:
    nhom = [x.strip() for x in args.nhom.split(",") if x.strip()]
    return _chay(args, tinh_ma=args.tinh_ma, nhom=nhom)


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
    nhom = None if args.nhom in (None, "all") else [x.strip() for x in args.nhom.split(",")]
    return _chay(args, tinh_ma=args.ma, nhom=nhom)


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


NHOM_LLM = ["hanh_chinh_dan_cu", "lich_su_dia_danh", "di_tich", "le_hoi", "kinh_te_van_hoa", "con_nguoi"]


def cmd_nap_llm(args) -> int:
    """Nạp trả lời của LLM ngoài (du_lieu/llm_ra/<mã>.json) vào kho, xã nào đã nạp thì bỏ qua."""
    from . import quy_trinh
    from .nguon import trinh_duyet

    trinh_duyet.tat()
    quy_trinh.CHE_DO_LLM = "tep"
    kho = _kho(args)
    da = set() if args.lam_lai else kho.da_xu_ly_ds(",".join(sorted(NHOM_LLM)))
    ds = [p.stem for p in sorted(quy_trinh.LLM_RA.glob("*.json"))
          if p.stem not in da and (not args.ma or p.stem in args.ma)]
    dat = tong = 0
    for ma in ds:
        rows = kho.tim_don_vi(ma=ma, cap="xa")
        if rows:
            kq = chay_tinh(kho, rows[0]["tinh_ma"], ma=ma, nhom=NHOM_LLM, bo_qua_da_co=False)
            tong += len(kq)
            dat += sum(1 for k in kq if k.trang_thai == "dat")
    print(f"Đã nạp {len(ds)} xã · {dat}/{tong} trường đạt.")
    kho.dong()
    return 0


def cmd_nguon(args) -> int:
    """Chạy mọi nguồn `bang`/`adapter` của tỉnh + nguồn dùng chung (_chung.yaml)."""
    kho = _kho(args)
    cfg = cau_hinh.nguon_tinh("_chung").get("nguon", []) + cau_hinh.nguon_tinh(args.tinh_ma).get("nguon", [])
    chay = [n for n in cfg if n.get("loai") in ("bang", "adapter") and (not args.ma or n["ma"] in args.ma)]
    if not chay:
        print(f"Tỉnh {args.tinh_ma}: chưa có nguồn bang/adapter trong config/nguon/ (hoặc --ma không khớp).")
        return 1
    for n in chay:
        try:
            if n["loai"] == "bang":
                from .nguon import bang

                r = bang.nap(kho, n, args.tinh_ma)
                print(f"  {n['ma']}: {r['so_truong']} trường · {r['so_xa']} xã"
                      + (f" · không khớp {len(r['khong_khop'])}: {r['khong_khop'][:5]}" if r["khong_khop"] else ""))
            else:
                print(f"  {n['ma']}: {_chay_adapter(kho, n, args)}")
        except Exception as e:  # một nguồn hỏng không chặn nguồn khác
            print(f"  ✗ {n['ma']}: {type(e).__name__}: {e}")
    kho.dong()
    return 0


def _chay_adapter(kho, n: dict, args) -> dict:
    """Nguồn cần code riêng (site đặc thù). Thêm adapter mới: viết module + một nhánh ở đây."""
    import importlib

    mod = importlib.import_module(f".nguon.{n['module']}", __package__)
    if n["module"] == "ocop_news":
        return mod.nap_url(kho, n["url"], tinh_ma=args.tinh_ma)
    if n["module"] == "phap_ly":
        return mod.nap(kho, args.tep or n["tep"], tinh_ma=args.tinh_ma)
    return mod.nap(kho, tinh_ma=args.tinh_ma, gioi_han=args.gioi_han)


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
    x.add_argument("--toan-quoc", action="store_true", help="Chạy mọi xã/phường trong kho (mặc định khi không lọc)")
    x.add_argument("--gioi-han", type=int, default=None, help="Chỉ chạy N đơn vị đầu (chạy thử)")
    x.add_argument("--lam-lai", action="store_true", help="Bỏ qua trạng thái đã đạt, làm lại từ đầu")
    x.add_argument("--khong-trinh-duyet", action="store_true", help="Không mở Chrome (chỉ cache + HTTP tĩnh)")
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
    ti.add_argument("--xuat-nguon", action="store_true",
                    help="Không gọi Ollama: ghi đề bài LLM từng xã vào du_lieu/llm_vao/ (cho Claude/agent)")
    ti.add_argument("--llm-tu-tep", action="store_true",
                    help="Không gọi Ollama: nạp trả lời từ du_lieu/llm_ra/<mã>.json")
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

    ng = sub.add_parser("nguon", help="Chạy nguồn có cấu trúc (bang/adapter) khai báo trong config/nguon/")
    ng.add_argument("--tinh-ma", dest="tinh_ma", required=True, help="Mã tỉnh, vd 46")
    ng.add_argument("--ma", nargs="*", help="Chỉ chạy các nguồn này (mặc định: tất cả bang/adapter)")
    ng.add_argument("--tep", help="adapter phap_ly: đường dẫn PDF/Excel tải tay")
    ng.add_argument("--gioi-han", type=int, default=None, help="adapter: chỉ xét N sản phẩm (chạy thử)")
    ng.set_defaults(fn=cmd_nguon)

    nl = sub.add_parser("nap-llm", help="Nạp trả lời LLM ngoài từ du_lieu/llm_ra/ (qua cùng bước kiểm)")
    nl.add_argument("--ma", nargs="*", help="Chỉ nạp các mã này")
    nl.add_argument("--lam-lai", action="store_true", help="Nạp lại cả xã đã nạp")
    nl.set_defaults(fn=cmd_nap_llm)

    dm = sub.add_parser("do-mang", help="Dò request AJAX/API của một trang (SPA)")
    dm.add_argument("--url", required=True)
    dm.add_argument("--so-luong", type=int, default=40)
    dm.set_defaults(fn=cmd_do_mang)

    return p


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
