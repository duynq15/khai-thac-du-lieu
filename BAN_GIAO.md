# Bàn giao dữ liệu khai thác

Xuất: `uv run khai-thac xuat --dinh-dang json` và `--dinh-dang excel` → `du_lieu/ban_giao/ban_giao_<thời điểm>.{json,xlsx}`.

- **Excel** – cho người đọc: sheet *Hướng dẫn*, *Tổng hợp* (độ đầy đủ theo tỉnh), mỗi tỉnh một sheet
  (mỗi xã một dòng, cột tên tiếng Việt, ô vàng = cần duyệt), *Nguồn & bằng chứng* (link + câu gốc).
- **JSON** – cho hệ thống tiếp nhận. Mô tả dưới đây.

## Cấu trúc JSON (schema 1.0)

```jsonc
{
  "meta":   { "phien_ban_schema": "1.0", "xuat_luc": "2026-10-13T12:32:12", "so_don_vi": 645,
              "quy_uoc": { ... giải thích trạng thái, hạng nguồn, kiểu ... } },
  "schema": { "xa": [ { "khoa": "dan_so", "nhan": "Dân số (người)", "kieu": "so",
                        "nhom": "hanh_chinh_dan_cu", "nhan_nhom": "Hành chính – Dân cư",
                        "bat_buoc": false, "thuoc_tinh": null }, ... ],
              "tinh": [...], "thon": [...] },
  "nguon":  { "tinhthanhpho_xa": { "ten": "...", "url": "...", "muc": "B" }, ... },
  "don_vi": [
    { "ma": "00454", "ten": "Xã Đông Anh", "loai": "xa", "cap": "xa",
      "tinh_ma": "01", "tinh_ten": "Thành phố Hà Nội", "parent_ma": null,
      "truong": {
        "dan_so": { "gia_tri": 118183, "trang_thai": "dat", "diem_tin": 75, "nam_du_lieu": 2025,
                    "nguon": { "ma": "tinhthanhpho_xa", "ten": "...", "url": "...", "muc": "B",
                               "da_kiem_chung": true },
                    "trich_doan": "population = 118183", "ly_do_loi": null, "canh_bao": [] },
        "anh_bia": { "gia_tri": null, "trang_thai": "thieu", ... },
        ...
      } }
  ]
}
```

## Quy tắc mapping

| Mục | Cách dùng |
|---|---|
| `don_vi[].ma` | Khoá chính – mã ĐVHC (tỉnh 2 số, xã 5 số). Ổn định giữa các lần xuất. |
| `schema.<cap>[]` | Từ điển trường: tạo cột/thuộc tính theo `khoa`, hiển thị theo `nhan`, gom tab theo `nhom`. |
| `truong.<khoa>` | **Mọi đơn vị có đủ mọi khoá** của cấp; chưa có dữ liệu → `gia_tri: null`, `trang_thai: "thieu"`. |
| `gia_tri` theo `kieu` | `so` → number · `ngay` → `"YYYY-MM-DD"` · `danh_sach` → string[] · `ban_ghi` → object[] (thuộc tính theo `schema...thuoc_tinh`) · `toa_do` → `{lat, lon}` · còn lại → string. |
| `trang_thai` | `dat` dùng được · `cho_duyet` đưa vào hàng chờ duyệt · `loi` không dùng (xem `ly_do_loi`) · `thieu` chưa có. |
| `nguon.muc` | `A` chính thống · `B` báo chí/tổng hợp · `C` tham khảo. Màn duyệt 4b hiển thị hạng này. |
| `nguon.da_kiem_chung = false` | Dữ liệu nhập tay chưa đối chiếu văn bản gốc → chỉ dùng sau khi cán bộ duyệt. |
| `trich_doan` | Câu nguyên văn trong `nguon.url` làm bằng chứng (màn 4b/4c "có bằng chứng"). |
| `nam_du_lieu` | Năm của số liệu – dùng so ứng viên khi mâu thuẫn. |

Mỗi trường trong file là **giá trị tốt nhất** (đạt → hạng A>B>C → điểm tin → năm mới). Các ứng viên
khác vẫn nằm trong `du_lieu/khai_thac.sqlite` (bảng `ket_qua`) nếu cần dựng màn duyệt mâu thuẫn.

Đổi cấu trúc thì tăng `meta.phien_ban_schema`.
