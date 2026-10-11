# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/client/main.py'],
    pathex=['C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/client'],
    binaries=[],
    datas=[('C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/client/login_dialog.py', '.'), ('C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/client/chat_overlay.py', '.'), ('C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/client/roblox_api.py', '.'), ('C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/client/ws_client.py', '.'), ('C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/client/window_manager.py', '.'), ('C:/Users/vyach/.gemini/antigravity/scratch/roblox-chat/client/config_manager.py', '.')],
    hiddenimports=['websockets', 'websockets.legacy', 'websockets.legacy.client', 'websockets.asyncio', 'websockets.asyncio.client', 'PyQt5.sip', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets'],
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
    name='RoChat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
