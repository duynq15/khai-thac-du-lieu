#!/usr/bin/env bash
# ĐIỀU PHỐI QUA ĐÊM cho nhiều tỉnh — tự phục hồi, ưu tiên theo danh sách.
#   ./dieu-phoi.sh [danh-sach] [so-luong]
# Mặc định: ưu tiên Hải Phòng, Hà Nội, rồi Đà Nẵng, HCM, Cần Thơ, Huế.
# Mỗi lệnh có timeout (tự cắt khi treo) và tự chạy lại khi thoát mã 75.
# Chạy lại được: resume tiếp đúng chỗ.
set -u
cd "$(dirname "$0")" || exit 1
# Nạp BRAVE_API_KEY mà KHÔNG source cả .zshrc (zshrc zsh treo trong bash)
if [ -z "${BRAVE_API_KEY:-}" ] && [ -f "$HOME/.zshrc" ]; then
  eval "$(grep -E '^[[:space:]]*export BRAVE_API_KEY=' "$HOME/.zshrc" | tail -1)" 2>/dev/null || true
fi
mkdir -p logs
# Tiến trình tự thoát mã 75 khi một xã quá giờ (tránh treo Playwright) → gọi lại, resume tiếp.
chay_lai() { while :; do "$@"; rc=$?; [ "$rc" -ne 75 ] && return "$rc"; done; }

DS="${1:-31 01 48 79 92 46}"
N="${2:-6}"
NCAO="thong_tin_chung,sap_xep_2025,hanh_chinh_dan_cu"
DIEU_PHOI_LOG="logs/dieu-phoi.out"
BAO_CAO="logs/BAO-CAO-SANG.txt"

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$DIEU_PHOI_LOG"; }

: > "$DIEU_PHOI_LOG"
log "=== ĐIỀU PHỐI QUA ĐÊM · ${N} luồng · ưu tiên: $DS ==="
[ -z "${BRAVE_API_KEY:-}" ] && log "⚠ Thiếu BRAVE_API_KEY"

for T in $DS; do
  # ---- PHA 0: NGUỒN CÓ CẤU TRÚC (config/nguon/<T>.yaml + _chung.yaml) — rẻ, chạy trước ----
  log "### $T · PHA 0 (nguồn có cấu trúc)"
  timeout 3600 uv run khai-thac nguon --tinh-ma "$T" >> "logs/t$T-nguon.log" 2>&1 || true

  # ---- PHA A: CÀO (nóng cache) ----
  log "### $T · PHA A (cào, $N luồng)"
  for k in $(seq 0 $((N - 1))); do
    chay_lai timeout 2700 uv run khai-thac tinh --ma "$T" --khong-llm \
      --nhom "$NCAO" --shard "$k/$N" >> "logs/t$T-cao-$k.log" 2>&1 &
  done
  wait

  # Không còn pha LLM: đo 10/2026 trên 10 phường Huế, 15/15 ô LLM "đạt" đều sai
  # (tiêu đề tin thành lễ hội, số hộ lấy từ thông báo). Muốn thử lại: chạy tay pha LLM (README).
  log "  ✓ xong 0+A tỉnh $T — $(uv run khai-thac thong-ke --tinh-ma "$T" 2>/dev/null | sed -n '2p')"
done

# ---- PHA C: Thôn (OCOP/adapter đã chạy ở PHA 0 qua config/nguon) ----
log "### PHA C — Thôn"
for T in $DS; do
  timeout 1800 uv run khai-thac thon --tinh-ma "$T" --xuat >> "logs/t$T-thon.log" 2>&1 || true
done

# ---- XUẤT ----
log "### XUẤT bàn giao"
uv run khai-thac xuat --dinh-dang excel >> "$DIEU_PHOI_LOG" 2>&1
uv run khai-thac xuat --dinh-dang json  >> "$DIEU_PHOI_LOG" 2>&1

# ---- BÁO CÁO SÁNG ----
{
  echo "════════ BÁO CÁO SÁNG · $(date '+%Y-%m-%d %H:%M') ════════"
  echo "Danh sách: $DS"
  echo
  echo "── Tổng quan toàn quốc ──"
  uv run khai-thac thong-ke 2>/dev/null | tail -40
  echo
  echo "── Tệp bàn giao ──"
  ls -lh du_lieu/ban_giao/ | tail -6
} > "$BAO_CAO" 2>&1

log "=== HOÀN TẤT · $(date '+%H:%M:%S') · xem $BAO_CAO ==="
