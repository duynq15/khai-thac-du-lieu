"""Pool proxy dùng cho việc khai thác.

Cảnh báo: proxy công khai (free) thường chết nhanh, chậm, và KHÔNG đáng tin về
bảo mật — chỉ dùng cho việc đọc trang công khai, tuyệt đối không gửi dữ liệu
nội bộ hay thông tin đăng nhập qua chúng. Muốn chạy bền thì khai proxy trả phí
vào `du_lieu/proxy.txt` (mỗi dòng `host:port` hoặc `user:pass@host:port`).
"""

from __future__ import annotations

import random
from pathlib import Path

import httpx

from .http import AGENT, GOC_DU_LIEU

TEP_PROXY = GOC_DU_LIEU / "proxy.txt"


def _client(proxy: str | None = None) -> httpx.Client:
    # Ép IPv4 để tránh treo khi mạng chặn IPv6 (xem khai_thac/http.py)
    return httpx.Client(
        proxy=proxy,
        transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=1),
        headers={"User-Agent": AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(30.0, connect=15.0),
    )

# Danh sách nguồn proxy công khai (text, mỗi dòng ip:port)
NGUON_PROXY = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
]

# Endpoint nhẹ để kiểm tra proxy còn sống — dùng HTTPS để lọc cả proxy hỗ trợ CONNECT
KIEM_TRA_URL = "https://api.ipify.org?format=json"


def tai_proxy() -> int:
    """Tải proxy công khai từ các nguồn, gộp và ghi vào du_lieu/proxy.txt."""
    gom: set[str] = set()
    with _client() as c:
        for url in NGUON_PROXY:
            try:
                r = c.get(url)
                if r.status_code != 200:
                    continue
                for dong in r.text.splitlines():
                    dong = dong.strip()
                    if not dong or ":" not in dong:
                        continue
                    # Lấy phần host:port ở cuối (bỏ tiền tố http://)
                    dong = dong.replace("http://", "").replace("https://", "").strip("/")
                    if dong.startswith(("0.0.0.0", "127.", "localhost", "::", "10.", "192.168.")):
                        continue
                    gom.add(dong)
            except httpx.HTTPError:
                continue

    TEP_PROXY.parent.mkdir(parents=True, exist_ok=True)
    with open(TEP_PROXY, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(gom)))
    return len(gom)


def doc_proxy() -> list[str]:
    if not TEP_PROXY.is_file():
        return []
    ds = [d.strip() for d in TEP_PROXY.read_text(encoding="utf-8").splitlines() if d.strip()]
    return list(dict.fromkeys(ds))


def _url(proxy: str) -> str:
    proxy = proxy.strip()
    return proxy if proxy.startswith(("http://", "https://")) else f"http://{proxy}"


def kiem_tra(proxy: str, *, doi_giay: float = 8.0) -> bool:
    try:
        with _client(_url(proxy)) as c:
            r = c.get(KIEM_TRA_URL, timeout=doi_giay)
            return r.status_code == 200
    except httpx.HTTPError:
        return False


class PoolProxy:
    """Xoay vòng proxy, đánh dấu proxy chết để tạm ngưng dùng."""

    def __init__(self, danh_sach: list[str] | None = None):
        self.ds = list(danh_sach if danh_sach is not None else doc_proxy())
        random.shuffle(self.ds)
        self.da_chet: set[str] = set()
        self._i = 0

    def __len__(self) -> int:
        return len(self.ds)

    def con_song(self) -> int:
        return sum(1 for p in self.ds if p not in self.da_chet)

    def lay(self) -> str | None:
        """Lấy proxy kế tiếp còn sống; hết thì trả None (đi thẳng)."""
        if not self.ds:
            return None
        for _ in range(len(self.ds)):
            self._i = (self._i + 1) % len(self.ds)
            p = self.ds[self._i]
            if p not in self.da_chet:
                return _url(p)
        return None

    def danh_dau_chet(self, proxy: str) -> None:
        p = proxy.replace("http://", "").replace("https://", "")
        self.da_chet.add(p)

    def chon_cho_kiem_tra(self, so_luong: int) -> list[str]:
        random.shuffle(self.ds)
        return self.ds[:so_luong]


def kiem_tra_hang_loat(so_luong: int = 60) -> tuple[int, int]:
    """Kiểm tra song song bằng luồng, trả (số sống, số thử)."""
    from concurrent.futures import ThreadPoolExecutor

    ds = doc_proxy()
    if not ds:
        return 0, 0
    random.shuffle(ds)
    ds = ds[:so_luong]

    song: list[str] = []
    with ThreadPoolExecutor(max_workers=20) as tp:
        for proxy, ok in zip(ds, tp.map(kiem_tra, ds)):
            if ok:
                song.append(proxy)

    # Chỉ giữ proxy sống
    TEP_PROXY.write_text("\n".join(song), encoding="utf-8")
    return len(song), len(ds)
