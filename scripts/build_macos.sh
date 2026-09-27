#!/usr/bin/env bash
# DeskBot macOS Application and DMG Build Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

ARCH="$(uname -m)"
echo "============================================================"
echo " Building DeskBot for macOS (${ARCH})"
echo "============================================================"

# Ensure resources icons exist
if [ ! -f "resources/deskbot.icns" ]; then
    echo "Generating icons..."
    python3 -c "
import os, subprocess
from companion.ui.icon import create_tray_icon_image
os.makedirs('resources/deskbot.iconset', exist_ok=True)
specs = [
    (16, 'icon_16x16.png'), (32, 'icon_16x16@2x.png'),
    (32, 'icon_32x32.png'), (64, 'icon_32x32@2x.png'),
    (128, 'icon_128x128.png'), (256, 'icon_128x128@2x.png'),
    (256, 'icon_256x256.png'), (512, 'icon_256x256@2x.png'),
    (512, 'icon_512x512.png'), (1024, 'icon_512x512@2x.png'),
]
for sz, fname in specs:
    create_tray_icon_image('ready', size=sz).save(os.path.join('resources/deskbot.iconset', fname), 'PNG')
subprocess.run(['iconutil', '-c', 'icns', 'resources/deskbot.iconset', '-o', 'resources/deskbot.icns'], check=True)
import shutil; shutil.rmtree('resources/deskbot.iconset')
"
fi

# Clean previous build artifacts
rm -rf build/DeskBot dist/DeskBot dist/DeskBot.app dist/*.dmg

echo "[1/3] Packaging application bundle with PyInstaller..."
pyinstaller --clean -y build/deskbot-macos.spec

if [ ! -d "dist/DeskBot.app" ]; then
    echo "ERROR: dist/DeskBot.app was not created!"
    exit 1
fi

echo "[2/3] Preparing DMG staging directory with drag-and-drop link..."
DMG_STAGING="dist/dmg_staging"
rm -rf "${DMG_STAGING}"
mkdir -p "${DMG_STAGING}"

cp -R "dist/DeskBot.app" "${DMG_STAGING}/"
ln -s /Applications "${DMG_STAGING}/Applications"

DMG_NAME="DeskBot-macOS-${ARCH}.dmg"
DMG_PATH="dist/${DMG_NAME}"
rm -f "${DMG_PATH}"

echo "[3/3] Creating compressed DMG disk image: ${DMG_PATH}..."
hdiutil create \
    -volname "DeskBot" \
    -srcfolder "${DMG_STAGING}" \
    -ov \
    -format UDZO \
    "${DMG_PATH}"

rm -rf "${DMG_STAGING}"

echo "============================================================"
echo " Build successful!"
echo " App bundle: dist/DeskBot.app"
echo " DMG image:  ${DMG_PATH} ($(du -sh "${DMG_PATH}" | cut -f1))"
echo "============================================================"
