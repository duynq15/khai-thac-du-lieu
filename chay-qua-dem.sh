#!/usr/bin/env bash
# Cào QUA ĐÊM cho nhiều tỉnh/thành, tối ưu:
#   Pha A: cào TẤT CẢ tỉnh trước (6 luồng/tỉnh, nóng cache — việc mạng, song song được)
#   Pha B: LLM TẤT CẢ tỉnh sau (1 luồng/tỉnh — GPU chạy một mình)
#   Pha C: OCOP + Thôn
#   Pha D: thống kê + xuất Excel/JSON
# Chạy lại được: phần đã xong tự bỏ qua (đánh dấu resume).
#
#   ./chay-qua-dem.sh                         # 9 thành phố trực thuộc TW (mặc định)
#   ./chay-qua-dem.sh "01 31 48 79 92 46"     # 6 thành phố
#   ./chay-qua-dem.sh "01 31" 8               # danh sách + số luồng cào
set -u

DANH_SACH="${1:-01 31 48 79 92 46 22 24 75}"
N="${2:-6}"
mkdir -p logs
# Tiến trình tự thoát mã 75 khi một xã quá giờ (tránh treo Playwright) → gọi lại, resume tiếp.
chay_lai() { while :; do "$@"; rc=$?; [ "$rc" -ne 75 ] && return "$rc"; done; }
T0=$SECONDS
# Nạp BRAVE_API_KEY mà KHÔNG source cả .zshrc (zshrc zsh treo trong bash)
if [ -z "${BRAVE_API_KEY:-}" ] && [ -f "$HOME/.zshrc" ]; then
  eval "$(grep -E '^[[:space:]]*export BRAVE_API_KEY=' "$HOME/.zshrc" | tail -1)" 2>/dev/null || true
fi
[ -z "${BRAVE_API_KEY:-}" ] && echo "⚠ Chưa có BRAVE_API_KEY (tìm kiếm sẽ lùi về scrape, dễ bị chặn)"

echo "=== QUA ĐÊM: [$DANH_SACH] · ${N} luồng cào/tỉnh ==="
echo "Bắt đầu: $(date '+%H:%M:%S')"

# ---------------------------------------------------------------- PHA A: CÀO
echo "### PHA A — CÀO ($(date '+%H:%M'))"
for T in $DANH_SACH; do
  echo "--- tỉnh $T ($(date '+%H:%M')) ---"
  for k in $(seq 0 $((N - 1))); do
    chay_lai uv run khai-thac tinh --ma "$T" --khong-llm \
      --nhom thong_tin_chung,sap_xep_2025,hanh_chinh_dan_cu \
      --shard "$k/$N" > "logs/t$T-cao-$k.log" 2>&1 &
  done
  wait
  uv run khai-thac thong-ke --tinh-ma "$T" | sed -n '2p'
done

# --------------------------------------------------------------- PHA B: LLM
echo "### PHA B — OLLAMA nội dung, 1 luồng/tỉnh ($(date '+%H:%M'))"
for T in $DANH_SACH; do
  echo "--- tỉnh $T ($(date '+%H:%M')) ---"
  chay_lai uv run khai-thac tinh --ma "$T" --shard 0/1 --khong-trinh-duyet \
    --nhom hanh_chinh_dan_cu,lich_su_dia_danh,di_tich,le_hoi,kinh_te_van_hoa,con_nguoi \
    > "logs/t$T-ollama.log" 2>&1
  tail -1 "logs/t$T-ollama.log"
done

# ------------------------------------------------------ PHA C: OCOP + Thôn
echo "### PHA C — OCOP + Thôn ($(date '+%H:%M'))"
for T in $DANH_SACH; do
  uv run khai-thac nongsan --tinh-ma "$T" > "logs/t$T-ocop.log" 2>&1 || true
  uv run khai-thac thon --tinh-ma "$T" --xuat > "logs/t$T-thon.log" 2>&1 || true
done

# --------------------------------------------------- PHA D: thống kê + xuất
echo "### PHA D — Thống kê & xuất ($(date '+%H:%M'))"
for T in $DANH_SACH; do
  echo "  • tỉnh $T:"; uv run khai-thac thong-ke --tinh-ma "$T" | sed -n '2p'
done
uv run khai-thac xuat --dinh-dang excel
uv run khai-thac xuat --dinh-dang json

echo "=== XONG · mất $(( (SECONDS - T0) / 3600 ))h $(( ((SECONDS - T0) % 3600) / 60 ))m · $(date '+%H:%M:%S') ==="
