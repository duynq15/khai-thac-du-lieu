"""Tải trang có render JavaScript (cho cổng *.gov.vn dựng bằng SPA).

Dùng Playwright với kênh Chrome có sẵn trên máy (không phải tải thêm trình duyệt).
Nếu chưa cài Playwright thì tầng này tự tắt và pipeline chạy bằng HTTP tĩnh.
Kèm vài dấu hiệu chống nhận diện bot và xoay proxy nếu pool đang bật.
"""

from __future__ import annotations

import random

from .van_ban import rut_van_ban

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
]

TU_CHAN = ("captcha", "xác minh", "unusual traffic", "just a moment", "verify you are human")


_tat = False  # --khong-trinh-duyet: pha LLM chỉ dùng cache + HTTP tĩnh

def tat() -> None:
    global _tat
    _tat = True

def san_sang() -> bool:
    if _tat:
        return False
    try:
        import playwright.sync_api  # noqa: F401

        return True
    except ImportError:
        return False

_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
         "--disable-blink-features=AutomationControlled"]

# Dùng lại MỘT Chrome cho cả phiên. Khi bật proxy, mỗi tiến trình gắn CỐ ĐỊNH một
# proxy cho trình duyệt (không đổi giữa chừng vì Playwright không cho đổi proxy của
# browser đang chạy) — chỉ đổi khi proxy chết/bị chặn.
_pl = None
_browser = None
_browser_proxy = "__chua__"   # proxy đang gắn với Chrome
_proxy_mong_muon = None       # proxy cố định của phiên trình duyệt


def _dang_proxy() -> bool:
    from ..http import dang_dung_proxy

    return dang_dung_proxy()


def _proxy_cho_browser():
    global _proxy_mong_muon
    if not _dang_proxy():
        return None
    if _proxy_mong_muon is None:
        from ..http import proxy_hien_tai

        _proxy_mong_muon = proxy_hien_tai()
    return _proxy_mong_muon


def _cau_hinh_proxy(proxy: str | None) -> dict | None:
    """Chuyển 'user:pass@host:port' hoặc 'host:port' thành cấu hình Playwright."""
    if not proxy:
        return None
    proxy = proxy if proxy.startswith(("http://", "https://")) else f"http://{proxy}"
    from urllib.parse import unquote, urlparse

    p = urlparse(proxy)
    cau: dict = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        cau["username"] = unquote(p.username)
    if p.password:
        cau["password"] = unquote(p.password)
    return cau


def _lay_browser():
    global _pl, _browser, _browser_proxy
    mong = _proxy_cho_browser()
    if _browser is not None and _browser_proxy == mong:
        return _browser
    dong_browser()
    from playwright.sync_api import sync_playwright

    _pl = sync_playwright().start()
    _browser = _pl.chromium.launch(channel="chrome", headless=True, args=_ARGS,
                                   proxy=_cau_hinh_proxy(mong))
    _browser_proxy = mong
    return _browser


def doi_proxy_browser() -> None:
    """Bỏ proxy/Chrome hiện tại để lần sau chọn proxy khác (khi bị chặn)."""
    global _proxy_mong_muon
    _proxy_mong_muon = None
    dong_browser()


def dong_browser() -> None:
    """Đóng Chrome dùng chung (gọi khi kết thúc chương trình)."""
    global _pl, _browser, _browser_proxy
    try:
        if _browser is not None:
            _browser.close()
    except Exception:
        pass
    try:
        if _pl is not None:
            _pl.stop()
    except Exception:
        pass
    _browser = None
    _pl = None
    _browser_proxy = "__chua__"


def _cho_trang(page) -> None:
    """Chờ vừa đủ: networkidle tối đa 3s + nghỉ ngẫu nhiên ngắn (SPA hay chậm)."""
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:
        pass
    page.wait_for_timeout(random.randint(300, 800))


def _doc_mot_trang(b, url: str, doi_giay: int) -> str:
    ctx = b.new_context(
        locale="vi-VN",
        user_agent=random.choice(UA_LIST),
        viewport={"width": 1366, "height": 900},
    )
    try:
        trang = ctx.new_page()
        trang.goto(url, wait_until="domcontentloaded", timeout=doi_giay * 1000)
        _cho_trang(trang)
        try:
            van_ban = trang.inner_text("body")
        except Exception:
            van_ban = ""
        if len(van_ban) < 200:
            van_ban = rut_van_ban(trang.content())
        return van_ban
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def lay_mang(url: str, *, doi_giay: int = 30) -> list[dict]:
    """Mở trang và ghi lại mọi request mạng (kèm body POST) để lộ endpoint AJAX/API.

    Trả [{'method','type','url','body'}].
    """
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return []

    ghi: list[dict] = []
    try:
        ctx = _lay_browser().new_context(locale="vi-VN", user_agent=random.choice(UA_LIST))
        try:
            page = ctx.new_page()

            def _them(req):
                try:
                    ghi.append({
                        "method": req.method, "type": req.resource_type, "url": req.url,
                        "body": (req.post_data or "")[:600],
                    })
                except Exception:
                    pass

            page.on("request", _them)
            page.goto(url, wait_until="domcontentloaded", timeout=doi_giay * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(2500)  # chờ các call AJAX muộn
            # Bấm nút phân trang/"xem thêm" để lộ request AJAX của danh sách
            for sel in (".pagination a", ".paging a", "a.next", "[rel=next]",
                        "a:has-text('Tiếp')", "a:has-text('Xem thêm')"):
                try:
                    phan = page.query_selector_all(sel)
                    if phan:
                        phan[-1].click(timeout=3000)
                        page.wait_for_timeout(3000)
                        break
                except Exception:
                    continue
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    except Exception:
        pass
    return ghi


def loc_ajax(ghi: list[dict]) -> list[dict]:
    """Lọc các request có khả năng là AJAX/API."""
    kq = []
    for r in ghi:
        ul = r["url"].lower()
        if r["type"] in ("xhr", "fetch") or ".json" in ul or "/api" in ul or "graphql" in ul:
            kq.append(r)
    return kq


def _bi_chan(van_ban: str) -> bool:
    return any(t in van_ban[:2000].lower() for t in TU_CHAN)


def lay_html(url: str, *, doi_giay: int = 25) -> str | None:
    """Trả HTML đã render (để dò liên kết menu). Dùng lại Chrome."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return None
    try:
        ctx = _lay_browser().new_context(
            locale="vi-VN", user_agent=random.choice(UA_LIST),
            viewport={"width": 1366, "height": 900},
        )
        try:
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=doi_giay * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(500)
            return page.content()
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    except Exception:
        return None


def doc_trang(url: str, *, doi_giay: int = 25, kenh: str = "chrome") -> dict | None:
    """Trả {'url', 'van_ban'} hoặc None. Dùng lại Chrome; đổi proxy nếu bị chặn."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return None

    for _ in range(2):
        try:
            chu = _doc_mot_trang(_lay_browser(), url, doi_giay)
        except Exception:
            chu = ""
        if chu and len(chu) >= 100 and not _bi_chan(chu):
            return {"url": url, "van_ban": chu}
        # Hỏng hoặc bị chặn: bỏ proxy/browser hiện tại rồi thử lại bằng proxy khác
        doi_proxy_browser()
    return None
