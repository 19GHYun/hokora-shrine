# -*- coding: utf-8 -*-
"""
exe 빌드: dist\\hokora.exe

  python build.py
  python build.py --print-version

아이콘(app.ico)은 코드로 그린 레이무 얼굴로 빌드 때마다 새로 만든다.
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENTRY = HERE / "hokora.pyw"
BUILD_DIR = HERE / "build"
ICON = BUILD_DIR / "app.ico"
EXE_NAME = "hokora"
PRODUCT = "Hokora"
COPYRIGHT = "Copyright (c) 2026 YGH. MIT License."
ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]
_qt_app = None

VERSION_TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={vt}, prodvers={vt}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'YGH'),
      StringStruct('FileDescription', {product!r}),
      StringStruct('FileVersion', {version!r}),
      StringStruct('InternalName', {exe!r}),
      StringStruct('LegalCopyright', {copyright!r}),
      StringStruct('OriginalFilename', {exe_file!r}),
      StringStruct('ProductName', {product!r}),
      StringStruct('ProductVersion', {version!r})])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def read_version() -> str:
    text = (HERE / "hokora" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"(\d+\.\d+\.\d+)"', text, re.M)
    if not m:
        raise SystemExit('hokora/__init__.py 에서 __version__ = "x.y.z" 를 찾지 못했습니다.')
    return m.group(1)


def write_icon(path: Path) -> None:
    """앱 아이콘을 PNG 항목으로 된 다중 크기 .ico 로."""
    from PySide6.QtCore import QBuffer, QIODevice, QSize
    from PySide6.QtWidgets import QApplication
    sys.path.insert(0, str(HERE))
    from hokora.app import app_icon
    global _qt_app  # 아이콘을 그리는 동안 QApplication 이 살아 있어야 함
    _qt_app = QApplication.instance() or QApplication([])
    icon = app_icon()
    blobs = []
    for s in ICO_SIZES:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        icon.pixmap(QSize(s, s)).toImage().save(buf, "PNG")
        blobs.append(bytes(buf.data()))
    offset = 6 + 16 * len(ICO_SIZES)
    head = struct.pack("<HHH", 0, 1, len(ICO_SIZES))
    for s, b in zip(ICO_SIZES, blobs):
        head += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    path.write_bytes(head + b"".join(blobs))


def main() -> int:
    version = read_version()
    if len(sys.argv) > 1 and sys.argv[1] == "--print-version":
        print(version)
        return 0
    BUILD_DIR.mkdir(exist_ok=True)
    write_icon(ICON)
    version_file = BUILD_DIR / "version_info.txt"
    version_file.write_text(VERSION_TEMPLATE.format(
        vt=tuple(int(x) for x in version.split(".")) + (0,), version=version, product=PRODUCT,
        exe=EXE_NAME, exe_file=f"{EXE_NAME}.exe", copyright=COPYRIGHT), encoding="utf-8")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
           "--name", EXE_NAME,
           "--icon", str(ICON),
           "--version-file", str(version_file),
           # AI 등으로 만든 캐릭터 그림 (없는 캐릭터는 코드 그림)
           "--add-data", f"{HERE / 'hokora' / 'sprites'}{';' if sys.platform == 'win32' else ':'}hokora/sprites",
           "--specpath", str(BUILD_DIR),
           str(ENTRY)]
    print(f"{PRODUCT} {version} 빌드 중…", flush=True)
    rc = subprocess.call(cmd, cwd=HERE)
    if rc == 0:
        print(f"완료: {HERE / 'dist' / (EXE_NAME + '.exe')}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
