#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
echo "Project dir: $PROJECT_DIR"

echo "[i] Top 30 largest files in project:"
du -ah "$PROJECT_DIR" | sort -hr | head -n 30 || true

mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/screenshots" "$PROJECT_DIR/runtime"
find "$PROJECT_DIR/logs" -type f -name "*.log" -mtime +7 -delete || true
find "$PROJECT_DIR/screenshots" -type f -mtime +7 -delete || true

find "$PROJECT_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + || true
find "$PROJECT_DIR" -type d -name ".pytest_cache" -prune -exec rm -rf {} + || true
find "$PROJECT_DIR" -type d -name ".mypy_cache" -prune -exec rm -rf {} + || true

[ -d "$PROJECT_DIR/runtime/pw-cache" ] && rm -rf "$PROJECT_DIR/runtime/pw-cache"

KEEP_N="${KEEP_N:-20}"
ls -1t "$PROJECT_DIR/logs"/*.log 2>/dev/null | tail -n +$((KEEP_N+1)) | xargs -r rm -f
ls -1t "$PROJECT_DIR/screenshots"/*.png 2>/dev/null | tail -n +$((KEEP_N+1)) | xargs -r rm -f

echo "[✓] Cleanup complete."
