#!/usr/bin/env python3
"""
RoChat Build Script — собирает клиент и сервер в standalone .exe файлы.

Использование:
    python build.py              # Собрать клиент и сервер
    python build.py --client     # Только клиент
    python build.py --server     # Только сервер
"""

import argparse
import os
import shutil
import subprocess
import sys

# Обеспечиваем корректную печать Unicode в Windows консоли
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")


def ensure_pyinstaller():
    """Убедиться, что PyInstaller установлен."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[*] Устанавливаю PyInstaller...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            stdout=subprocess.DEVNULL,
        )


def ensure_deps():
    """Установить все зависимости."""
    print("[*] Устанавливаю зависимости...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "PyQt5>=5.15", "websockets>=12.0", "requests>=2.31", "pyinstaller>=6.0",
    ])


def build_client():
    """Собрать клиент в RoChat.exe."""
    import PyInstaller.__main__

    print()
    print("=" * 50)
    print("  [>] Сборка RoChat Client -> RoChat.exe")
    print("=" * 50)

    client_dir = os.path.join(ROOT, "client")

    icon_path = os.path.join(ROOT, "assets", "icon.ico")
    icon_args = ["--icon", icon_path] if os.path.exists(icon_path) else []

    args = [
        os.path.join(client_dir, "main.py"),
        "--onefile",
        "--windowed",                  # Без консольного окна
        "--name=RoChat",
        f"--paths={client_dir}",
        f"--add-data={os.path.join(client_dir, 'login_dialog.py')};.",
        f"--add-data={os.path.join(client_dir, 'chat_overlay.py')};.",
        f"--add-data={os.path.join(client_dir, 'roblox_api.py')};.",
        f"--add-data={os.path.join(client_dir, 'ws_client.py')};.",
        f"--add-data={os.path.join(client_dir, 'window_manager.py')};.",
        f"--add-data={os.path.join(client_dir, 'config_manager.py')};.",
        "--hidden-import=websockets",
        "--hidden-import=websockets.legacy",
        "--hidden-import=websockets.legacy.client",
        "--hidden-import=websockets.asyncio",
        "--hidden-import=websockets.asyncio.client",
        "--hidden-import=PyQt5.sip",
        "--hidden-import=PyQt5.QtCore",
        "--hidden-import=PyQt5.QtGui",
        "--hidden-import=PyQt5.QtWidgets",
        f"--distpath={DIST}",
        f"--workpath={os.path.join(BUILD, 'client')}",
        f"--specpath={BUILD}",
        "--clean",
        "--noconfirm",
    ] + icon_args

    PyInstaller.__main__.run(args)

    exe_path = os.path.join(DIST, "RoChat.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n[OK] Клиент собран: {exe_path} ({size_mb:.1f} MB)")
    else:
        print("\n[ERR] Ошибка сборки клиента!")
        sys.exit(1)


def build_server():
    """Собрать сервер в RoChat_Server.exe."""
    import PyInstaller.__main__

    print()
    print("=" * 50)
    print("  [>] Сборка RoChat Server -> RoChat_Server.exe")
    print("=" * 50)

    server_dir = os.path.join(ROOT, "server")

    args = [
        os.path.join(server_dir, "server.py"),
        "--onefile",
        "--console",                   # С консольным окном (для логов)
        "--name=RoChat_Server",
        "--hidden-import=websockets",
        "--hidden-import=websockets.legacy",
        "--hidden-import=websockets.legacy.server",
        "--hidden-import=websockets.asyncio",
        "--hidden-import=websockets.asyncio.server",
        f"--distpath={DIST}",
        f"--workpath={os.path.join(BUILD, 'server')}",
        f"--specpath={BUILD}",
        "--clean",
        "--noconfirm",
    ]

    PyInstaller.__main__.run(args)

    exe_path = os.path.join(DIST, "RoChat_Server.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n[OK] Сервер собран: {exe_path} ({size_mb:.1f} MB)")
    else:
        print("\n[ERR] Ошибка сборки сервера!")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="RoChat Build Script")
    parser.add_argument("--client", action="store_true", help="Собрать только клиент")
    parser.add_argument("--server", action="store_true", help="Собрать только сервер")
    parser.add_argument("--skip-deps", action="store_true", help="Не устанавливать зависимости")
    args = parser.parse_args()

    build_all = not args.client and not args.server

    print("=== RoChat Build System ===")

    if not args.skip_deps:
        ensure_deps()
        ensure_pyinstaller()

    os.makedirs(DIST, exist_ok=True)

    if build_all or args.client:
        build_client()

    if build_all or args.server:
        build_server()

    print()
    print("=" * 50)
    print("  [+] Сборка завершена успешно!")
    print(f"  [+] Папка с исполняемыми файлами: {DIST}")
    print("=" * 50)

    if build_all or (args.client and args.server):
        print(f"  - RoChat.exe        (Клиент - чат оверлей)")
        print(f"  - RoChat_Server.exe (Relay сервер)")
    elif args.client:
        print(f"  - RoChat.exe        (Клиент - чат оверлей)")
    else:
        print(f"  - RoChat_Server.exe (Relay сервер)")


if __name__ == "__main__":
    main()
