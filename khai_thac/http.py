"""HTTP client: delay ngẫu nhiên, xoay User-Agent, xoay proxy, phát hiện chặn.

Chống bị chặn/captcha bằng bốn lớp:
  1. Giãn nhịp ngẫu nhiên giữa hai lần gọi cùng một tên miền.
  2. Xoay User-Agent mỗi lần gọi.
  3. Xoay proxy nếu bật pool (xem khai_thac/proxy.py).
  4. Phát hiện 403/429/captcha rồi đổi proxy và lùi dần.
"""

from __future__ import annotations

import random
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

AGENT = "XaPhuongVietNam-KhaiThac/0.1 (+https://xaphuongvietnam.vn)"
GOC_DU_LIEU = Path(__file__).resolve().parent.parent / "du_lieu"

# Xoay User-Agent: giả lập trình duyệt phổ biến để giảm dấu vết bot
UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

# Nhịp tối thiểu (giây) giữa hai lần gọi cùng một tên miền
NHIP_DO = {
    "tinhthanhpho.com": 1.0,
    "www.tinhthanhpho.com": 1.0,
    "34tinhthanh.com": 0.5,
    "provinces.open-api.vn": 0.3,
    "photon.komoot.io": 1.0,
    "vi.wikipedia.org": 0.6,
    "duckduckgo.com": 2.5,
    "lite.duckduckgo.com": 2.5,
    "nongsan.haiphong.gov.vn": 0.3,
    "ocop.gov.vn": 0.5,
}
NHIP_DO_MAC_DINH = 1.0
# Hệ số ngẫu nhiên cho nhịp: chờ = nhip * U(1.0, 2.2) + U(0.1, 0.9)
NGAU_NHIEN = (1.0, 2.2)
# Hệ số nhân chung cho độ trễ (đặt qua --nhanh khi phát triển, mặc định 1.0)
_he_so_jitter = 1.0


def dat_he_so_jitter(x: float) -> None:
    global _he_so_jitter
    _he_so_jitter = max(0.0, x)

# Dấu hiệu bị chặn / captcha
TU_CHAN = (
    "captcha", "xác minh", "unusual traffic", "are you a robot", "access denied",
    "cf-chl", "just a moment", "verify you are human", "vui lòng xác nhận",
    "cloudflare", "request blocked", "too many requests",
)

_lan_goi_cuoi: dict[str, float] = {}
_clients: dict[str, httpx.Client] = {}
_dung_proxy = False
_pool = None  # khai_thac.proxy.PoolProxy, do CLI gắn vào


def bat_proxy(pool) -> None:
    global _dung_proxy, _pool
    _dung_proxy = True
    _pool = pool


def tat_proxy() -> None:
    global _dung_proxy
    _dung_proxy = False


def _transport() -> httpx.HTTPTransport:
    # Ép IPv4: nhiều mạng chặn IPv6 khiến httpx treo ở bước kết nối (curl không gặp
    # vì nó thử IPv4 trước). Bind 0.0.0.0 buộc socket dùng IPv4 nên kết nối tức thì.
    return httpx.HTTPTransport(local_address="0.0.0.0", retries=0)


# Timeout mặc định NGẮN để host bị "blackhole" không treo luồng.
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)


def client(proxy: str | None = None) -> httpx.Client:
    """Client theo proxy (httpx chỉ cho đặt proxy ở mức client, không theo request)."""
    key = proxy or "_truc_tiep"
    c = _clients.get(key)
    if c is None:
        c = httpx.Client(
            proxy=proxy,
            transport=_transport(),
            follow_redirects=True,
            timeout=_TIMEOUT,
        )
        _clients[key] = c
    return c


def _chon_ua() -> str:
    return random.choice(UA_LIST)


def _cho(host: str) -> None:
    nhip = NHIP_DO.get(host, NHIP_DO_MAC_DINH)
    truoc = _lan_goi_cuoi.get(host)
    if truoc is not None:
        con = nhip - (time.monotonic() - truoc)
        if con > 0:
            time.sleep(con * _he_so_jitter)
    # Thêm độ trễ ngẫu nhiên để không lộ nhịp đều đặn
    if _he_so_jitter > 0:
        time.sleep((nhip * random.uniform(*NGAU_NHIEN) + random.uniform(0.1, 0.9)) * _he_so_jitter)
    _lan_goi_cuoi[host] = time.monotonic()


def la_chan(r: httpx.Response | None) -> bool:
    if r is None:
        return False
    if r.status_code in (403, 429, 503):
        return True
    if r.status_code == 200:
        dau = r.text[:2000].lower()
        return any(t in dau for t in TU_CHAN)
    return False


def _lay_proxy() -> str | None:
    if _dung_proxy and _pool is not None and len(_pool):
        return _pool.lay()
    return None


def proxy_hien_tai() -> str | None:
    """Proxy kế tiếp để tầng trình duyệt dùng chung pool với tầng HTTP."""
    return _lay_proxy()


def dang_dung_proxy() -> bool:
    return _dung_proxy and _pool is not None and len(_pool) > 0


# --- Ngoại tuyến: pha LLM chỉ đọc cache, không gọi mạng ---
_ngoai_tuyen = False

def dat_ngoai_tuyen(bat: bool = True) -> None:
    global _ngoai_tuyen
    _ngoai_tuyen = bat

def ngoai_tuyen() -> bool:
    return _ngoai_tuyen

# --- Tự động chuyển sang proxy khi bị chặn ---
_tu_dong_proxy = False
_dang_chuan_bi = False
_lan_chuan_bi = 0.0


def bat_tu_dong_proxy(bat: bool = True) -> None:
    global _tu_dong_proxy
    _tu_dong_proxy = bat


def _chuan_bi_proxy_nen() -> None:
    """Tải + kiểm tra proxy ở luồng nền rồi bật pool (không chặn luồng chính)."""
    global _dang_chuan_bi, _lan_chuan_bi
    if _dang_chuan_bi or not _tu_dong_proxy:
        return
    if time.time() - _lan_chuan_bi < 900:   # tối đa 15 phút một lần
        return
    _dang_chuan_bi = True

    def _lam() -> None:
        global _dang_chuan_bi, _lan_chuan_bi
        try:
            from . import proxy as pm

            if not pm.doc_proxy():
                pm.tai_proxy()
            pm.kiem_tra_hang_loat(80)
            ds = pm.doc_proxy()
            if ds and not dang_dung_proxy():
                bat_proxy(pm.PoolProxy(ds))
        except Exception:
            pass
        finally:
            _lan_chuan_bi = time.time()
            _dang_chuan_bi = False

    threading.Thread(target=_lam, daemon=True).start()


def goi(
    url: str,
    *,
    params: dict | None = None,
    thu_lai: int = 4,
    headers: dict | None = None,
    timeout: float | None = None,
) -> httpx.Response | None:
    """GET có thử lại, xoay UA/proxy, lùi dần khi bị chặn. Trả None nếu hỏng hẳn (hoặc ngoại tuyến)."""
    if _ngoai_tuyen:
        return None
    host = urlparse(url).netloc
    for lan in range(thu_lai):
        _cho(host)
        proxy = _lay_proxy()
        h = {"User-Agent": _chon_ua(), "Accept-Language": "vi,en;q=0.8"}
        if headers:
            h.update(headers)
        try:
            r = client(proxy).get(
                url, params=params, headers=h,
                timeout=(timeout if timeout is not None else _TIMEOUT),
            )
        except httpx.HTTPError:
            if proxy and _pool is not None:
                _pool.danh_dau_chet(proxy)
            time.sleep(1.0 * (lan + 1))
            continue

        if la_chan(r):
            if proxy and _pool is not None:
                _pool.danh_dau_chet(proxy)
            # Tự động chuẩn bị proxy nếu đang ở chế độ đó
            _chuan_bi_proxy_nen()
            # Bị chặn: lùi dần rồi thử lại (lần sau đổi proxy)
            time.sleep(2.5 * (lan + 1))
            continue

        if r.status_code == 200:
            return r
        if r.status_code in (500, 502, 504):
            time.sleep(1.5 * (lan + 1))
            continue
        return r
    return None


def json_goi(url: str, *, params: dict | None = None, thu_lai: int = 4,
             timeout: float | None = None):
    r = goi(url, params=params, thu_lai=thu_lai, timeout=timeout)
    if r is None or r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def html_goi(url: str, *, params: dict | None = None, thu_lai: int = 4,
             timeout: float | None = None) -> str | None:
    r = goi(url, params=params, thu_lai=thu_lai, timeout=timeout)
    if r is None or r.status_code != 200:
        return None
    return r.text
