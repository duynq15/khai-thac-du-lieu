# khai-thac-du-lieu

Bộ khai thác dữ liệu cho **Xã Phường Việt Nam**: lấy danh mục đơn vị hành chính,
thông tin chung, lịch sử – văn hoá – di tích – lễ hội, toạ độ và tin tức; kiểm
chứng trước khi bàn giao cho Laravel (`BE-LocalInitiative`).

Kế hoạch đầy đủ ở [`../KE-HOACH-KHAI-THAC-DU-LIEU.md`](../KE-HOACH-KHAI-THAC-DU-LIEU.md).

## Cách hoạt động

```
nguồn ngoài → nguon/ → trich_xuat/ → kiem_tra/ → store/ (SQLite) → xuat/ (JSON, Excel)
```

- `config/truong_du_lieu.yaml` — cấu hình từng trường theo cấp và nhóm.
- `config/nguon/<mã tỉnh>.yaml` — nguồn của từng tỉnh (mẫu cổng xã, bbox, danh sách nguồn);
  `config/nguon/_chung.yaml` — nguồn dùng cho mọi tỉnh. Xem mục **Thêm nguồn cho một tỉnh**.
- `config/nguon.yaml` — sổ đăng ký nguồn cũ (hạng A/B/C, nhịp gọi, miền chặn).
- `khai_thac/nguon/` — đọc nguồn: danh mục, wikipedia, tìm kiếm, tải trang, toạ độ.
- `khai_thac/trich_xuat/` — bóc giá trị: quy tắc tất định + LLM (Ollama).
- `khai_thac/kiem_tra.py` — bộ quy tắc kiểm (rỗng, danh sách, mã ĐVHC, ngày, số,
  email/điện thoại, URL, toạ độ trong lãnh thổ/tỉnh, trích dẫn có trong nguồn).
- `du_lieu/` — SQLite làm việc + JSON/Excel bàn giao.

## Chạy

```bash
cd khai-thac-du-lieu
uv sync

# 1. Danh mục toàn quốc: 34 tỉnh + 3.321 xã/phường
uv run khai-thac danh-muc --toan-quoc --xuat

# 2. Khai thác một xã theo nhóm
uv run khai-thac xa --ten "Đông Anh" --tinh "Hà Nội" --nhom thong_tin_chung --xuat json excel

# 2b. Gom thôn / tổ dân phố của xã (từ trang riêng của xã)
uv run khai-thac thon --ma 00454 --xuat
uv run khai-thac thon --ma 00454 --mien https://donganh.hanoi.gov.vn   # bỏ qua bước dò tìm kiếm

# 3. Xuất kết quả đã lưu
uv run khai-thac xuat --dinh-dang excel

# 4. Kiểm tra LLM nội bộ
uv run khai-thac trang-thai

# 5. Chống bị chặn: delay ngẫu nhiên + xoay proxy
uv run khai-thac proxy --tai                 # tải proxy công khai
uv run khai-thac proxy --kiem-tra 100        # giữ lại proxy còn sống
uv run khai-thac xa --ten "Đông Anh" --nhom thong_tin_chung --dung-proxy
uv run khai-thac xa --ten "Đông Anh" --nhom thong_tin_chung --nhanh   # chỉ khi phát triển
```

## Cào theo từng tỉnh/thành (khuyến nghị)

Mỗi tỉnh cào **toàn bộ nhóm** cho mọi xã, và **mỗi xã chỉ nạp nguồn 1 lần** rồi bóc
tất cả nhóm từ nguồn đó (không mở lại trang gov nhiều lần). Có cache trang, chạy
lại tự bỏ qua xã đã đủ nhóm.

```bash
# Một tỉnh (vd Hà Nội = 01): tất cả nhóm, xuất kết quả
uv run khai-thac tinh --ma 01 --xuat json excel

# Một tỉnh, chỉ vài nhóm
uv run khai-thac tinh --ma 01 --nhom thong_tin_chung,di_tich,le_hoi

# Một tỉnh, 4 luồng song song
for k in 0 1 2 3; do
  uv run khai-thac tinh --ma 01 --shard $k/4 > logs/hn-$k.log 2>&1 &
done; wait

# Qua đêm nhiều tỉnh: nguồn cấu trúc → cào → LLM → thôn → xuất (tự chạy tiếp khi treo)
setsid nohup ./dieu-phoi.sh "31 01 48 79 92 46" 6 > logs/dieu-phoi.run 2>&1 < /dev/null &
./giam-sat.sh "31 01 48 79 92 46"     # tuỳ chọn: tự khởi động lại dieu-phoi nếu chết
```

## Thêm nguồn cho một tỉnh (không viết code)

Mỗi tỉnh một tệp `config/nguon/<mã>.yaml` (vd `46.yaml` = Huế):

```yaml
ten: Huế
cong_xa: {mau: "https://{slug}.hue.gov.vn"}   # {slug}=tên bỏ tiền tố/dấu, {loai}=xa|phuong|dackhu
bbox: [15.9, 16.8, 107.0, 108.3]              # kiểm toạ độ "trong tỉnh"
nguon:
  - {ma: hue_svhttdl, loai: van_ban, url: "https://svhttdl.hue.gov.vn/di-san-van-hoa.html", muc: A}
  - ma: hue_bang_dan_so
    loai: bang                 # có cấu trúc → `khai-thac nguon`, không qua LLM
    dinh_dang: html            # json | html | pdf | xlsx
    url: https://...
    khoa_xa: {ten: "Tên đơn vị"}            # hoặc {ma: code} nếu nguồn có mã ĐVHC
    cot: {dan_so: "Dân số", dien_tich_km2: "Diện tích"}
    muc: A
```

- `bang`: chạy bằng `uv run khai-thac nguon --tinh-ma 46` (hoặc `--ma hue_bang_dan_so`).
  Trường đã đạt hạng A/B từ đây sẽ **không gửi LLM** nữa.
- `van_ban`: trang cấp tỉnh (danh mục di tích, lễ hội…) — khi khai thác từng xã, chỉ đoạn
  văn nhắc tên xã đó được đưa vào LLM.
- `adapter`: site cần code riêng (`module: nongsan` → `khai_thac/nguon/nongsan.py`).
- Tỉnh chưa có tệp vẫn chạy được (Wikipedia + tìm kiếm), chỉ kém hơn.
- Cổng xã đã dò lưu theo **mã** ở `du_lieu/cong_xa.json` (tên trùng giữa tỉnh không lẫn).

Hồ sơ chạy nằm ở `config/chay.yaml` (phạm vi, nhóm, chia lô, proxy, LLM, bàn giao).
Dòng lệnh ghi đè được.

## Chạy toàn quốc (một lượt, không chia tỉnh)

Hồ sơ chạy nằm ở `config/chay.yaml` (phạm vi, nhóm, chia lô, proxy, LLM, bàn giao).
Dòng lệnh ghi đè được.

```bash
# Khai thác toàn quốc nhóm "thông tin chung", chia lô 150, nghỉ 60s giữa lô.
# Mặc định BỎ QUA đơn vị đã đạt → chạy lại là chạy tiếp, không làm lại.
uv run khai-thac xa --nhom thong_tin_chung --toan-quoc

# Chạy thử 20 đơn vị đầu
uv run khai-thac xa --nhom thong_tin_chung --toan-quoc --gioi-han 20

# Làm lại từ đầu (không bỏ qua)
uv run khai-thac xa --nhom thong_tin_chung --toan-quoc --lam-lai

# Gợi ý: bật proxy trước khi chạy toàn quốc
uv run khai-thac proxy --tai && uv run khai-thac proxy --kiem-tra 150
# rồi đặt mang.dung_proxy: true trong config/chay.yaml (hoặc thêm --dung-proxy)
```

Tiến trình và kết quả nằm trong `du_lieu/khai_thac.sqlite`; `xuat` lấy **một** giá trị
tốt nhất mỗi trường (đạt → hạng A>B>C → điểm tin → năm số liệu → mới nhất). Các ứng viên
khác vẫn trong kho cho màn duyệt mâu thuẫn.

## Tìm kiếm (Brave Search API)

Nút thắt lớn nhất khi khai thác là bị search engine chặn. Cách giải quyết: dùng
**Brave Search API** (ổn định, JSON, không bị chặn). Không có khoá thì tự lùi về
scrape DuckDuckGo/Bing.

```bash
export BRAVE_API_KEY="khoá_của_bạn"    # hoặc dán vào config/chay.yaml: tim_kiem.brave_api_key
uv run khai-thac trang-thai             # kiểm tra: "Brave Search API: đã có khoá"
```

Hạn mức free ~2.000 truy vấn/tháng; xã đã cache tên miền gov thì không gọi lại.

## Chống bị chặn / captcha

- **Delay ngẫu nhiên**: mỗi lần gọi cùng một miền chờ `nhip × U(1.0, 2.2) + U(0.1, 0.9)`.
  Cờ `--nhanh` hạ hệ số xuống 0.15 để chạy thử (không dùng khi khai thác thật).
- **Xoay User-Agent** mỗi request (danh sách trong `khai_thac/http.py`).
- **Xoay proxy**: `proxy --tai` tải danh sách công khai, `--kiem-tra N` loại cái chết,
  `--dung-proxy` bật xoay khi chạy. Proxy chết tự bị tạm ngưng.
- **Phát hiện chặn**: gặp 403/429 hoặc trang chứa dấu hiệu captcha thì đổi proxy và lùi dần.
- **Ép IPv4**: bind `0.0.0.0` tránh treo khi mạng chặn IPv6 (lỗi hay gặp, httpx rất chậm nếu không ép).

> Proxy công khai chết nhanh và không đáng tin bảo mật — chỉ dùng để đọc trang công
> khai. Muốn bền thì khai proxy trả phí vào `du_lieu/proxy.txt`.


## LLM nội bộ (tuỳ chọn)

Phần LLM dùng Ollama; thiếu Ollama thì pipeline vẫn chạy bằng quy tắc.

```bash
ollama pull qwen2.5:7b-instruct
ollama serve
```

## Bàn giao sang Laravel

`xuat_json` sinh tệp trong `du_lieu/ban_giao/`. Phía Laravel đọc tệp này bằng
lệnh artisan (xem kế hoạch, mục 5) để ghi vào `khai_thac_ket_qua`, rồi cán bộ
duyệt trên web-admin trước khi vào bảng nghiệp vụ.

## Danh mục tới đâu?

| Cấp | Nguồn | Ghi chú |
|---|---|---|
| Tỉnh/thành (34) | API `open-api.vn` + `34tinhthanh` + `tinhthanhpho` | chính xác, có đối chiếu chéo |
| Xã/phường (3.321) | như trên | chính xác, có `merger_details` |
| **Thôn/tổ dân phố** | **crawl trang riêng của từng xã** (`khai-thac thon`) | **không có API quốc gia**; độ phủ tuỳ xã; kết quả là đề xuất để duyệt |

Vì nhà nước chưa công bố danh mục thôn dạng API, thôn phải đọc từ trang mỗi xã
(hoặc nhập tay/Excel). Tên miền trang xã được dò một lần rồi **nhớ vào
`du_lieu/mien_gov.json`**; có thể truyền thẳng bằng `--mien`.

