
import configparser
import os
import subprocess
import sys
from pathlib import Path

from database import Database

# 用户自定义 .desktop 文件目录
CUSTOM_APPS_DIR = Path.home() / ".local/share/applications"
# 数据库文件路径
DB_PATH = Path.home() / ".config/gpu-selector/gpu_selector.db"

def scan_apps(db: Database):
    # 扫描 .desktop 文件并更新数据库
    system_paths = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
        Path("/var/lib/flatpak/exports/share/applications"),
    ]
    user_path = CUSTOM_APPS_DIR
    definitive_apps = {}

    # 遍历系统应用路径
    for path in system_paths:
        if path.exists():
            for root, _, files in os.walk(path):
                for file in files:
                    if file.endswith(".desktop"):
                        definitive_apps[file] = Path(root) / file

    # 遍历用户应用路径，用户路径下的文件会覆盖系统路径下的同名文件
    if user_path.exists():
        for root, _, files in os.walk(user_path):
            for file in files:
                if file.endswith(".desktop"):
                    definitive_apps[file] = Path(root) / file

    # 解析并存储应用数据到数据库
    for basename, full_path in definitive_apps.items():
        _parse_and_store(db, basename, full_path)

    return len(definitive_apps)

def _parse_and_store(db: Database, basename: str, file_path: Path):
    # 解析 .desktop 文件并存储到数据库
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(file_path, encoding='utf-8')
        if 'Desktop Entry' in parser:
            entry = parser['Desktop Entry']
            # 忽略没有名称或设置为不显示的应用
            if not entry.get('Name') or entry.getboolean('NoDisplay', fallback=False):
                return

            # 判断应用是否已被用户自定义
            is_customized = (file_path.parent == CUSTOM_APPS_DIR)

            # 收集应用数据
            app_data = {
                "basename": basename,
                "full_path": str(file_path),
                "app_name": entry.get('Name'),
                "app_comment": entry.get('Comment'),
                "app_exec": entry.get('Exec'),
                "is_customized": is_customized or entry.getboolean('PrefersNonDefaultGPU', fallback=False)
            }
            # 插入或更新数据库中的应用
            db.upsert_app(app_data)
    except Exception:
        # 忽略解析错误
        pass

def _find_app_by_identifier(db: Database, identifier: str):
    # 根据ID或名称查找应用
    if identifier.isdigit():
        try:
            # 如果是数字ID，从排序后的列表中查找
            app_index = int(identifier)
            apps = db.get_apps()
            if 0 <= app_index < len(apps):
                return apps[app_index]
        except (ValueError, IndexError):
            return None
    else:
        # 如果是名称，通过数据库查找
        return db.find_app(identifier)

def set_nvidia(db: Database, identifier: str):
    # 设置应用优先使用NVIDIA GPU
    app = _find_app_by_identifier(db, identifier)
    if not app:
        return None, f"Application '{identifier}' not found."

    original_path = Path(app['full_path'])
    custom_path = CUSTOM_APPS_DIR / app['basename']

    # 创建自定义应用目录
    CUSTOM_APPS_DIR.mkdir(parents=True, exist_ok=True)

    # 解析原始 .desktop 文件
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(original_path, encoding='utf-8')

    if not parser.has_section('Desktop Entry'):
        return None, f"Invalid .desktop file: no [Desktop Entry] in {original_path}"

    # 设置 PrefersNonDefaultGPU 属性为 true
    parser.set('Desktop Entry', 'PrefersNonDefaultGPU', 'true')

    # 将修改后的内容写入用户自定义目录
    with open(custom_path, 'w', encoding='utf-8') as f:
        parser.write(f, space_around_delimiters=False)

    # 更新数据库中的自定义状态
    db.update_customized_status(app['basename'], True)
    # 刷新桌面数据库
    _refresh_desktop_database()
    # 重新扫描以更新应用路径
    scan_apps(db)
    return app['app_name'], None

def unset_nvidia(db: Database, identifier: str):
    # 重置应用为默认GPU偏好
    app = _find_app_by_identifier(db, identifier)
    if not app:
        return None, f"Application '{identifier}' not found."

    custom_path = CUSTOM_APPS_DIR / app['basename']
    app_name = app['app_name']

    # 如果存在自定义文件，则删除
    if custom_path.exists():
        custom_path.unlink()
        # 更新数据库中的自定义状态
        db.update_customized_status(app['basename'], False)
        # 刷新桌面数据库
        _refresh_desktop_database()
        return app_name, None
    else:
        return None, f"Application '{app_name}' was not customized."

def _refresh_desktop_database():
    # 尝试更新桌面数据库
    try:
        subprocess.run(["update-desktop-database", str(CUSTOM_APPS_DIR)], check=True, capture_output=True)
    except Exception:
        # 静默处理错误
        pass
