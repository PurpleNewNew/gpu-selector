import sqlite3

class Database:
    def __init__(self, db_path="gpu_selector.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_table()

    def create_table(self):
        cursor = self.conn.cursor()
        # 创建应用表，basename 作为唯一标识
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                basename TEXT NOT NULL UNIQUE,
                full_path TEXT NOT NULL,
                app_name TEXT NOT NULL,
                app_comment TEXT,
                app_exec TEXT,
                is_customized BOOLEAN DEFAULT 0
            )
        ''')
        self.conn.commit()

    def upsert_app(self, app_data):
        sql = '''
            INSERT INTO apps (basename, full_path, app_name, app_comment, app_exec, is_customized)
            VALUES (:basename, :full_path, :app_name, :app_comment, :app_exec, :is_customized)
            ON CONFLICT(basename) DO UPDATE SET
                full_path = excluded.full_path,
                app_name = excluded.app_name,
                app_comment = excluded.app_comment,
                app_exec = excluded.app_exec,
                is_customized = excluded.is_customized;
        '''
        cursor = self.conn.cursor()
        # 插入或更新应用数据
        cursor.execute(sql, app_data)
        self.conn.commit()

    def get_apps(self):
        # 获取所有应用，按名称排序
        cursor = self.conn.cursor()
        sql = "SELECT * FROM apps ORDER BY app_name COLLATE NOCASE"
        cursor.execute(sql)
        return cursor.fetchall()

    def find_app(self, name_query):
        # 根据名称查找单个应用（模糊匹配）
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM apps WHERE app_name LIKE ? LIMIT 1", (f'%{name_query}%',))
        return cursor.fetchone()

    def update_customized_status(self, basename, is_customized):
        # 更新应用的自定义状态
        cursor = self.conn.cursor()
        cursor.execute("UPDATE apps SET is_customized = ? WHERE basename = ?", (is_customized, basename))
        self.conn.commit()

    def close(self):
        # 关闭数据库连接
        self.conn.close()
