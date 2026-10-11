# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/server/server.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['websockets', 'websockets.legacy', 'websockets.legacy.server', 'websockets.asyncio', 'websockets.asyncio.server'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RoChat_Server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
