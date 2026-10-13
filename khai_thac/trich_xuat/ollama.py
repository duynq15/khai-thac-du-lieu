"""Trích xuất bằng LLM chạy nội bộ (Ollama).

Nguyên tắc: model chỉ được lấy thông tin có trong đoạn nguồn; không có thì trả
null. Hậu kiểm trích dẫn nằm ở tầng kiểm tra, không tin lời model.
"""

from __future__ import annotations

import json
import os

import httpx

OLLAMA = "http://localhost:11434"
MODEL_MAC_DINH = "qwen2.5:3b-instruct"


def san_sang() -> bool:
    try:
        r = httpx.get(f"{OLLAMA}/api/tags", timeout=2.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def ds_model() -> list[str]:
    try:
        r = httpx.get(f"{OLLAMA}/api/tags", timeout=3.0)
        if r.status_code == 200:
            return [m.get("name", "") for m in (r.json().get("models") or [])]
    except httpx.HTTPError:
        pass
    return []


# Placeholder theo kiểu để model không chép nhầm chữ kiểu vào giá trị
_PH = {
    "van_ban": '"<chuỗi>"',
    "so": 0,
    "danh_sach": '["<mục>"]',
    "ngay": '"YYYY-MM-DD"',
    "email": '"a@b.com"',
    "url": '"https://..."',
    "dien_thoai": '"0xxxxxxxxx"',
    "ma_so": '"<mã>"',
}


def _mau(t: dict) -> str:
    """Mẫu giá trị theo kiểu; bản ghi liệt kê đúng thuộc tính cần bóc."""
    if t.get("kieu") == "ban_ghi":
        tt = ", ".join(f'"{k}": "<chuỗi hoặc null>"' for k in t.get("thuoc_tinh") or ["ten"])
        return f"[{{{tt}}}]"
    return _PH.get(t.get("kieu", "van_ban"), "<giá trị>")


def _prompt(van_ban: str, truong: list[dict]) -> str:
    # Liệt kê trường dạng JSON tường minh — model nhỏ hiểu đúng hơn nhiều so với mô tả suông
    dong = "\n".join(f'  "{t["khoa"]}": {_mau(t)}' for t in truong)
    return (
        "Bóc thông tin từ văn bản tiếng Việt về một đơn vị hành chính.\n"
        "CHỈ lấy thông tin CÓ trong văn bản; nếu không có thì đặt gia_tri = null.\n"
        "Giá trị phải CỤ THỂ (tên di tích, tên lễ hội, tên làng nghề…), "
        "KHÔNG dùng tên xã/phường hay câu chung chung.\n"
        "Trường dạng mảng object: mỗi di tích/lễ hội là MỘT object, thuộc tính không có thì null.\n"
        "Với mỗi trường tìm được, kèm trich_doan là câu NGUYÊN VĂN trong văn bản làm bằng chứng, "
        "và nam là năm số liệu nếu văn bản nêu (vd 2024), không có thì null.\n\n"
        "Các trường cần bóc (đúng tên khoá):\n"
        f"{{\n{dong}\n}}\n\n"
        "Trả về DUY NHẤT JSON đúng dạng:\n"
        '{"ket_qua": [{"khoa": "<tên khoá>", "gia_tri": <giá trị>, "trich_doan": "<câu trong văn bản>", "nam": 2024}]}\n\n'
        "VĂN BẢN:\n"
        f"{van_ban[:8000]}\n"
    )


def _cau_hinh() -> dict:
    from .. import cau_hinh

    return {
        "nha": (cau_hinh.lay_ho_so("llm", "nha_cung_cap", mac_dinh="ollama") or "ollama").lower(),
        "model": cau_hinh.lay_ho_so("llm", "model", mac_dinh=MODEL_MAC_DINH) or MODEL_MAC_DINH,
        "endpoint": (cau_hinh.lay_ho_so("llm", "endpoint", mac_dinh=OLLAMA) or OLLAMA).rstrip("/"),
        "base_url": (cau_hinh.lay_ho_so("llm", "base_url", mac_dinh="") or "").rstrip("/"),
        "api_key": os.environ.get("LLM_API_KEY")
        or cau_hinh.lay_ho_so("llm", "api_key", mac_dinh="") or "",
    }


def _tach_du(du: dict) -> dict[str, dict]:
    kq: dict[str, dict] = {}
    for mot in du.get("ket_qua") or []:
        khoa = mot.get("khoa")
        if khoa:
            td = mot.get("trich_doan")
            if isinstance(td, list):
                td = " ".join(str(x) for x in td)
            nam = mot.get("nam")
            kq[khoa] = {"gia_tri": mot.get("gia_tri"), "trich_doan": td,
                        "nam": nam if isinstance(nam, int) and 1900 < nam < 2100 else None}
    return kq


def _goi_ollama(van_ban: str, truong: list[dict], model: str, cfg: dict, timeout: float) -> dict:
    try:
        r = httpx.post(
            f"{cfg['endpoint']}/api/generate",
            json={
                "model": model,
                "prompt": _prompt(van_ban, truong),
                "format": "json",
                "stream": False,
                "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 2048},
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            print(f"    ! Ollama HTTP {r.status_code}: {r.text[:120]}", flush=True)
            return {}
        return _tach_du(json.loads(r.json().get("response", "{}")))
    except httpx.TimeoutException:
        print(f"    ! Ollama quá {timeout:.0f}s (GPU có chạy không? `ollama ps`)", flush=True)
        return {}
    except (httpx.HTTPError, ValueError) as e:
        print(f"    ! Ollama lỗi {type(e).__name__}: {str(e)[:120]}", flush=True)
        return {}


def _goi_openai(van_ban: str, truong: list[dict], model: str, cfg: dict, timeout: float) -> dict:
    """Dịch vụ OpenAI-compatible (OpenAI, Gemini, gateway, …)."""
    if not cfg["base_url"]:
        return {}
    try:
        r = httpx.post(
            f"{cfg['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": _prompt(van_ban, truong)}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return {}
        noi = r.json()["choices"][0]["message"]["content"]
        return _tach_du(json.loads(noi))
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return {}


def boc(van_ban: str, truong: list[dict], *,
        model: str | None = None, timeout: float = 120.0) -> dict[str, dict]:
    """Trích xuất; tự chọn nhà cung cấp theo config (ollama | openai)."""
    cfg = _cau_hinh()
    model = model or cfg["model"]
    if cfg["nha"] == "openai" and cfg["base_url"]:
        return _goi_openai(van_ban, truong, model, cfg, timeout)
    if not san_sang():
        return {}
    return _goi_ollama(van_ban, truong, model, cfg, timeout)
