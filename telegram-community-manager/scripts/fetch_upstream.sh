#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_URL="https://github.com/Nayan-Bebale/Telegram-Member-Migration-Tool.git"
UPSTREAM_COMMIT="0619887480abe6a19b6652e8a8aafe6ceaa93a66"
DEST="${1:-vendor/Nayan-Telegram-Member-Migration-Tool}"

if [ -e "$DEST" ]; then
  echo "Destination already exists: $DEST" >&2
  exit 1
fi

git clone --no-checkout "$UPSTREAM_URL" "$DEST"
git -C "$DEST" checkout --detach "$UPSTREAM_COMMIT"
echo "Pinned upstream checked out at $DEST"
