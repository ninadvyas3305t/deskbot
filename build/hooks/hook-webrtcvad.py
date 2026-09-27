"""Custom PyInstaller hook for webrtcvad to support webrtcvad-wheels distribution package."""

from PyInstaller.utils.hooks import copy_metadata

datas = []
for pkg in ("webrtcvad", "webrtcvad-wheels", "webrtcvad_wheels"):
    try:
        datas += copy_metadata(pkg)
        break
    except Exception:
        pass
