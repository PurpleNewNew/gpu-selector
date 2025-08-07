import re
import sys
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, ListView, ListItem, Static

# 将项目根目录添加到路径中以允许导入
sys.path.append(str(Path(__file__).parent))

from core import DB_PATH, set_nvidia, unset_nvidia
from database import Database

# 检查是否在PyInstaller打包环境中
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # 如果是打包环境，CSS文件在_MEIPASS目录下
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    # 否则，CSS文件在脚本的同级目录
    BUNDLE_DIR = Path(__file__).parent

class TUI(App):
    TITLE = "GPU Selector"
    CSS_PATH = BUNDLE_DIR / "tui.css"

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("space", "toggle_setting", "Set/Unset"),
        ("r", "refresh_table", "Refresh"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, db_path):
        super().__init__()
        self.db = Database(db_path=db_path)
        self.apps = []
        self.displayed_keys = []
        self.quit_counter = 0

    def compose(self) -> ComposeResult:
        # 创建UI组件
        yield Static(self.TITLE, id="header")
        yield Horizontal(
            Vertical(
                ListView(
                    ListItem(Static("[b]GPU 设置[/b]"), id="gpu-settings")
                ),
                id="sidebar"
            ),
            Vertical(
                Input(placeholder="搜索 (支持正则表达式)..."),
                DataTable(id="app-table", cursor_type="cell"),
                id="main-content"
            )
        )

    def on_mount(self) -> None:
        # 应用挂载时调用
        self.action_refresh_table()
        self.query_one(Input).focus()

    def on_input_changed(self, message: Input.Changed) -> None:
        # 搜索框内容改变时调用
        self.filter_apps(message.value)

    def _get_app_by_original_index(self, index_str: str):
        # 通过原始索引从self.apps列表中查找应用
        try:
            return self.apps[int(index_str)]
        except (IndexError, ValueError, TypeError):
            return None

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_toggle_setting(self) -> None:
        # 切换选中应用NVIDIA设置
        table = self.query_one(DataTable)
        if not (0 <= table.cursor_row < len(self.displayed_keys)):
            return

        original_index_str = self.displayed_keys[table.cursor_row]
        app = self._get_app_by_original_index(original_index_str)

        if not app:
            self.notify("错误: 找不到应用", title="错误", severity="error")
            return

        app_name_to_toggle = app['app_name']

        if app['is_customized']:
            name, err = unset_nvidia(self.db, original_index_str)
        else:
            name, err = set_nvidia(self.db, original_index_str)

        if err:
            self.notify(f"错误: {err}", title="操作失败", severity="error")
        else:
            self.notify(f"成功切换 '{name}'.", title="操作成功")
            # 记住光标位置
            cursor_row = table.cursor_row
            self.action_refresh_table()
            # 尝试恢复光标位置
            if cursor_row < table.row_count:
                table.move_cursor(row=cursor_row)

    def action_refresh_table(self) -> None:
        # 重新加载应用数据并刷新表格
        self.apps = self.db.get_apps()
        self.filter_apps(self.query_one(Input).value)
        self.notify("应用列表已刷新")

    def action_quit(self) -> None:
        # 处理退出请求
        self.quit_counter += 1
        if self.quit_counter == 1:
            self.notify("再按一次退出", timeout=1)
            self.set_timer(1, self._reset_quit_counter)
        elif self.quit_counter >= 2:
            self.exit()

    def _reset_quit_counter(self) -> None:
        # 重置退出计数器
        self.quit_counter = 0


    def filter_apps(self, search_term: str):
        # 根据搜索词过滤表格 (支持正则)
        table = self.query_one(DataTable)
        current_cursor_key = None
        if 0 <= table.cursor_row < len(self.displayed_keys):
            current_cursor_key = self.displayed_keys[table.cursor_row]

        table.clear()
        self.displayed_keys.clear()

        if not table.columns:
            table.add_columns("ID", "状态", "应用名称", "备注")

        try:
            search_re = re.compile(search_term, re.IGNORECASE)
        except re.error:
            search_re = re.compile(re.escape(search_term), re.IGNORECASE)

        # 过滤并填充数据
        matched_apps = []
        for index, app in enumerate(self.apps):
            if search_re.search(app['app_name']):
                matched_apps.append((index, app))

        for i, (original_index, app) in enumerate(matched_apps):
            status = "[✔]" if app['is_customized'] else "[ ]"
            key = str(original_index)
            table.add_row(str(i + 1), status, app['app_name'], app['app_comment'] or "", key=key)
            self.displayed_keys.append(key)

        # 刷新后尝试恢复光标
        if current_cursor_key in self.displayed_keys:
            new_row = self.displayed_keys.index(current_cursor_key)
            table.move_cursor(row=new_row)
        elif self.displayed_keys:
            table.move_cursor(row=0)

if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    app = TUI(db_path=str(DB_PATH))
    app.run()
