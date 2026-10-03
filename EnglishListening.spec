# Build on Windows x64 using: pyinstaller --noconfirm --clean EnglishListening.spec
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata
from deno import find_deno_bin

if sys.platform != 'win32':
    raise RuntimeError('Build the Windows EXE on Windows, not Linux.')

datas, binaries, hiddenimports = [], [], []
for package in (
    'faster_whisper', 'ctranslate2', 'av', 'onnxruntime', 'tokenizers',
    'yt_dlp', 'yt_dlp_ejs', 'keyring',
    'nvidia.cublas', 'nvidia.cudnn', 'nvidia.cuda_nvrtc',
):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
for distribution in ('faster-whisper', 'yt-dlp', 'yt-dlp-ejs', 'deno', 'keyring'):
    datas += copy_metadata(distribution)
binaries.append((find_deno_bin(), '.'))
hiddenimports += ['keyring.backends.Windows', 'win32timezone', 'tkinter', 'tkinter.ttk']

a = Analysis(['app.py'], pathex=[SPECPATH], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
             excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='EnglishListening',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='EnglishListening')
