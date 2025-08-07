import argparse
import sys
from pathlib import Path

from core import (DB_PATH, scan_apps, set_nvidia, unset_nvidia)
from database import Database

def run_scan(db: Database):
    print("Scanning and updating application database...")
    count = scan_apps(db)
    print(f"Scan complete. Found {count} unique applications.")

def run_list(db: Database):
    apps = db.get_apps()
    if not apps:
        print("No applications found. Run 'scan' first.")
        return

    print(f"{ 'ID':<4} {'NVIDIA':<8} {'APP NAME':<40} {'COMMENT'}")
    print("-" * 80)
    for index, app in enumerate(apps, 1):
        status = "[*]" if app['is_customized'] else "[ ]"
        print(f"{index:<4} {status:<8} {app['app_name']:<40} {app['app_comment'] or ''}")

def run_set(db: Database, identifier: str):
    print(f"Setting '{identifier}' to prefer NVIDIA GPU...")
    name, err = set_nvidia(db, identifier)
    if err:
        print(f"Error: {err}", file=sys.stderr)
    else:
        print(f"Successfully set '{name}' to prefer the NVIDIA GPU.")

def run_unset(db: Database, identifier: str):
    print(f"Resetting '{identifier}' to default GPU preference...")
    name, err = unset_nvidia(db, identifier)
    if err:
        print(f"Error: {err}", file=sys.stderr)
    else:
        print(f"Successfully reset '{name}'.")

def run_install_service():
    """创建并安装 systemd 用户服务文件。"""
    # 获取当前可执行文件的绝对路径
    # 在PyInstaller打包后，sys.argv[0]就是可执行文件本身的路径
    executable_path = Path(sys.argv[0]).resolve()
    service_name = "gpu-selector-scan"

    # 定义要监控的目录
    app_dirs_to_watch = [
        Path.home() / ".local/share/applications",
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
        Path("/var/lib/flatpak/exports/share/applications"),
    ]

    # systemd .service 文件模板
    service_template = f"""
[Unit]
Description=Scan for applications for GPU Selector

[Service]
Type=oneshot
ExecStart={executable_path} scan
"""

    # systemd .path 文件模板
    path_template = f"""
[Unit]
Description=Monitor application directories for changes to trigger GPU Selector scan

[Path]
"""
    for app_dir in app_dirs_to_watch:
        if app_dir.exists():
            path_template += f"PathChanged={app_dir}\n"

    path_template += "\n[Install]\nWantedBy=default.target\n"

    # 写入文件
    systemd_user_dir = Path.home() / ".config/systemd/user"
    systemd_user_dir.mkdir(parents=True, exist_ok=True)

    service_file_path = systemd_user_dir / f"{service_name}.service"
    path_file_path = systemd_user_dir / f"{service_name}.path"

    service_file_path.write_text(service_template)
    path_file_path.write_text(path_template)

    print("✅ Systemd service files created successfully!")
    print("To enable and start the automatic scanning, run the following commands:")
    print("\n  systemctl --user daemon-reload")
    print(f"  systemctl --user enable --now {service_name}.path")

def run_uninstall_service():
    """卸载 systemd 用户服务文件。"""
    service_name = "gpu-selector-scan"
    systemd_user_dir = Path.home() / ".config/systemd/user"
    service_file = systemd_user_dir / f"{service_name}.service"
    path_file = systemd_user_dir / f"{service_name}.path"

    if not service_file.exists() and not path_file.exists():
        print("Service files not found. Nothing to do.")
        return

    print("Disabling and removing service files...")
    # 停止服务
    os.system(f"systemctl --user disable --now {service_name}.path > /dev/null 2>&1")

    # 删除文件
    if service_file.exists():
        service_file.unlink()
    if path_file.exists():
        path_file.unlink()

    print("✅ Service files removed.")
    print("Please run the following command to apply the changes:")
    print("\n  systemctl --user daemon-reload")


def run_tui():
    try:
        from tui import TUI
    except ImportError:
        print("Error: 'textual' is not installed. Please run 'pip install textual' to use the TUI.", file=sys.stderr)
        sys.exit(1)

    app = TUI(db_path=str(DB_PATH))
    app.run()

def main():
    # 确保数据库目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path=str(DB_PATH))

    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(
        description="一个为Linux桌面应用管理GPU偏好的工具。\n推荐使用TUI模式进行交互，或使用CLI命令进行脚本化操作。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # 添加子命令解析器
    subparsers = parser.add_subparsers(dest='command', required=True, help='可用命令', metavar='COMMAND')

    # TUI 命令
    parser_tui = subparsers.add_parser('tui', help='运行交互式的TUI界面 (推荐)。')
    parser_tui.set_defaults(func=lambda args: run_tui())

    # CLI 命令
    parser_scan = subparsers.add_parser('scan', help='扫描系统和用户应用目录，以建立或更新本地应用数据库。')
    parser_scan.set_defaults(func=lambda args: run_scan(db))

    parser_list = subparsers.add_parser('list', help='列出所有检测到的应用及其当前的GPU偏好状态。')
    parser_list.set_defaults(func=lambda args: run_list(db))

    parser_set = subparsers.add_parser('set', help='为一个特定应用设置高性能GPU偏好 (接受应用名称或列表中的ID)。')
    parser_set.add_argument('app_name', help='要设置的应用名称或ID')
    parser_set.set_defaults(func=lambda args: run_set(db, args.app_name))

    parser_unset = subparsers.add_parser('unset', help='为一个特定应用恢复默认的GPU偏好 (接受应用名称或列表中的ID)。')
    parser_unset.add_argument('app_name', help='要恢复的应用名称或ID')
    parser_unset.set_defaults(func=lambda args: run_unset(db, args.app_name))

    # 服务管理命令
    parser_install = subparsers.add_parser('install-service', help='安装一个systemd用户服务，以在后台自动扫描应用变更。')
    parser_install.set_defaults(func=lambda args: run_install_service())

    parser_uninstall = subparsers.add_parser('uninstall-service', help='卸载并禁用systemd用户服务。')
    parser_uninstall.set_defaults(func=lambda args: run_uninstall_service())

    # 解析命令行参数并执行对应函数
    args = parser.parse_args()
    args.func(args)

    # 关闭数据库连接
    db.close()

if __name__ == "__main__":
    main()
