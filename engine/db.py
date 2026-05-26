# -*- coding: utf-8 -*-
"""
DataBox 数据库连接与迁移管理模块 (Database Connection & Migration Manager)
------------------------------------------------------------------------
这个模块负责：
1. 配置和初始化 DataBox 本地 SQLite 元数据库。
2. 建立与配置 SQLAlchemy ORM 引擎与会话工厂。
3. 实现连接获取的生成器函数（供 FastAPI 依赖注入使用）。
4. 在服务启动时，安全地执行数据库版本控制与结构平滑迁移（兼容老版本的手写 SQL 迁移并过渡到 Alembic 管理）。
"""

import sys
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from typing import Generator

# 1. 动态持久化路径解析
# 判断当前运行环境：是在打包后的桌面环境（Tauri Frozen/Sidecar）中，还是在本地源码开发环境中。
is_frozen = getattr(sys, "frozen", False)
if is_frozen:
    from engine.runtime_paths import private_runtime_dir
    # 打包运行：数据库保存在系统推荐的用户专有数据目录下，防止卸载或更新时丢失数据
    DB_PATH = private_runtime_dir("data") / "databox_local.db"
else:
    # 源码开发：直接保存在项目根目录下，方便开发者查看、调试、备份
    DB_PATH = Path(__file__).resolve().parent.parent / "databox_local.db"

# 构造标准 SQLite 连接 URL
DATABASE_URL = f"sqlite:///{DB_PATH}"

# 创建数据库物理引擎 (Database Engine)
# Python & SQLAlchemy 知识点:
#   - `create_engine`：创建物理连接引擎，它是所有数据库操作的核心通道。
#   - `check_same_thread: False`：SQLite 默认只允许创建连接的线程访问数据库。
#     但在 Web 开发（如 FastAPI）中，请求是由多线程/多协程并发处理的，因此必须关闭此安全锁。
engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# 创建本地数据库会话工厂 (Session Factory)
# autocommit=False: 开启事务管理，所有写操作必须显式调用 commit() 才会保存，防止数据写一半出错导致脏数据。
# autoflush=False: 关闭自动刷新，提升性能，避免频繁往数据库发送临时数据。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建声明式 ORM 模型基类 (Declarative Base)
# 项目中所有的实体模型类（如 User, DataSource, BackupRecord 等）都必须继承自这个 Base 基类，
# 这样 SQLAlchemy 才能识别并将它们映射到实际的数据库表中。
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话连接 (Database Session Generator)
    
    FastAPI 极其经典的依赖注入管道方法：
    Python 知识点:
      - `Generator[Session, None, None]`：类型注解，表示这是一个生成器，产生（yield）Session 对象，不接收输入，也没有最终返回值。
      - `yield` 关键字：在此处会暂停执行，将创建好的 `db` 会话交给 FastAPI 具体的 API 接口使用。
      - `finally` 块：无论接口执行成功还是中途抛出任何崩溃异常，FastAPI 结束请求时都会再次回到这里，
        执行 `db.close()`，确保连接绝对被关闭释放，从而彻底杜绝了数据库连接泄露（Connection Leak）的致命隐患！
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    数据库初始化与版本自动迁移迁移引擎
    
    在 main.py 的 lifespan 启动勾子中调用。
    它负责：
    1. 物理备份：修改表结构前，完整复制一份 `databox_local.db` 备用，防止迁移失败导致数据库损毁。
    2. 兼容清理：若检测到极早期开发时手写的 `schema_migrations` 老旧迁移记录，则自动执行 v1~v10 的 SQL 平滑迁移。
    3. 移交 Alembic：利用 stamp 标记为 baseline，完成对主流数据库迁移工具 Alembic 的平滑过渡。
    4. 执行 Alembic：自动升级（upgrade head）到当前代码对应的最新表结构。
    5. 容灾恢复：若发生任何无法恢复的异常，自动丢弃当前连接，从备份文件瞬间还原，保证系统稳定性。
    """
    from engine import models  # 必须在这里导入模型，确保所有映射关系已在 SQLAlchemy 中完成注册
    import shutil
    import time
    import sys
    from pathlib import Path
    from sqlalchemy import text
    from sqlalchemy.engine import Connection
    from alembic.config import Config
    from alembic import command

    # 1. 物理安全备份机制 (Secure Database Backup)
    backup_path = None
    if DB_PATH.exists():
        timestamp = int(time.time())
        backup_name = f"{DB_PATH.name}.bak_{timestamp}"
        backup_path = DB_PATH.with_name(backup_name)
        try:
            # 完整物理复制数据库文件
            shutil.copy2(DB_PATH, backup_path)
            
            # 回收历史备份：只保留最近 5 次的备份文件，多余的老旧备份自动清理删除，避免撑爆磁盘
            backups = sorted(DB_PATH.parent.glob(f"{DB_PATH.name}.bak_*"))
            if len(backups) > 5:
                for old_bak in backups[:-5]:
                    try:
                        old_bak.unlink()
                    except Exception:
                        pass
        except Exception as e:
            print(f"迁移警告：升级前未能成功备份元数据库文件: {e}")
            backup_path = None

    try:
        # 2. 动态计算 Alembic 配置文件及其脚本的绝对路径
        is_frozen = getattr(sys, "frozen", False)
        if is_frozen:
            # 打包运行环境下，Alembic 配置文件和脚本会被释放在临时解压目录（_MEIPASS）中
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                ini_path = Path(meipass) / "alembic.ini"
                script_location = Path(meipass) / "engine" / "migrations"
            else:
                exec_dir = Path(sys.executable).parent
                ini_path = exec_dir / "alembic.ini"
                script_location = exec_dir / "engine" / "migrations"
        else:
            # 源码运行环境下，路径位于开发工作区中
            ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
            script_location = Path(__file__).resolve().parent / "migrations"

        # 3. 创建 Alembic 运行时配置并动态重写目标参数
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("script_location", str(script_location))
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

        # 4. 检查当前本地数据库的历史结构状态
        has_legacy = False
        has_alembic = False
        with engine.begin() as conn:
            # 检查是否存在老版本手写迁移标志表 schema_migrations
            res = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"))
            has_legacy = res.fetchone() is not None

            # 检查是否存在 Alembic 标准迁移表 alembic_version
            res_alembic = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"))
            has_alembic = res_alembic.fetchone() is not None

        # ---------------------------------------------------------------------
        # 情景一：检测到处于历史过渡期的老数据库结构，执行渐进式手写 SQL 升级到 v10
        # ---------------------------------------------------------------------
        if has_legacy and not has_alembic:
            print("系统检测到极早期手写账本式的元数据库，启动 v1~v10 紧急平滑迁移...")

            # 辅助闭包函数：查询 SQLite 表结构，安全判断某个字段是否存在，避免重复 Alter 报错
            def has_column(conn: Connection, table: str, col: str) -> bool:
                res = conn.execute(text(f"PRAGMA table_info({table})"))
                return any(row[1] == col for row in res.fetchall())

            # 定义 v1 至 v10 串行小步快跑的升级 SQL 命令集
            def migration_v1(conn: Connection) -> None:
                # 升级 1: 支持 SSH 安全连接通道参数
                cols = {
                    "ssh_enabled": "INTEGER NOT NULL DEFAULT 0",
                    "ssh_host": "VARCHAR",
                    "ssh_port": "INTEGER NOT NULL DEFAULT 22",
                    "ssh_username": "VARCHAR",
                    "ssh_password_ciphertext": "VARCHAR",
                    "ssh_password_nonce": "VARCHAR",
                    "ssh_pkey_path": "VARCHAR",
                    "ssh_pkey_passphrase_ciphertext": "VARCHAR",
                    "ssh_pkey_passphrase_nonce": "VARCHAR",
                }
                for col_name, col_type in cols.items():
                    if not has_column(conn, "data_sources", col_name):
                        conn.execute(text(f"ALTER TABLE data_sources ADD COLUMN {col_name} {col_type}"))

            def migration_v2(conn: Connection) -> None:
                # 升级 2: 多环境划分支持 (开发、测试、生产) 与只读保护标志
                cols = {
                    "is_read_only": "INTEGER NOT NULL DEFAULT 0",
                    "env": "VARCHAR NOT NULL DEFAULT 'dev'",
                }
                for col_name, col_type in cols.items():
                    if not has_column(conn, "data_sources", col_name):
                        conn.execute(text(f"ALTER TABLE data_sources ADD COLUMN {col_name} {col_type}"))

            def migration_v3(conn: Connection) -> None:
                # 升级 3: LLM 请求大模型生成的 SQL 执行流水账中增加关联数据源
                if not has_column(conn, "llm_logs", "data_source_id"):
                    conn.execute(text("ALTER TABLE llm_logs ADD COLUMN data_source_id VARCHAR"))

            def migration_v4(conn: Connection) -> None:
                # 升级 4: 支持 MySQL SSL/TLS 双向安全加密网络通道
                cols = {
                    "ssl_enabled": "INTEGER NOT NULL DEFAULT 0",
                    "ssl_ca_path": "VARCHAR",
                    "ssl_cert_path": "VARCHAR",
                    "ssl_key_path": "VARCHAR",
                    "ssl_verify_identity": "INTEGER NOT NULL DEFAULT 1",
                }
                for col_name, col_type in cols.items():
                    if not has_column(conn, "data_sources", col_name):
                        conn.execute(text(f"ALTER TABLE data_sources ADD COLUMN {col_name} {col_type}"))

            def migration_v5(conn: Connection) -> None:
                # 升级 5: 增加大模型生成模板版本、温度、最大 Token 及结构合理性警告属性
                cols = {
                    "prompt_version": "VARCHAR",
                    "prompt_template_hash": "VARCHAR",
                    "model_temperature": "FLOAT",
                    "max_tokens": "INTEGER",
                    "schema_validation_warnings": "TEXT",
                }
                for col_name, col_type in cols.items():
                    if not has_column(conn, "llm_logs", col_name):
                        conn.execute(text(f"ALTER TABLE llm_logs ADD COLUMN {col_name} {col_type}"))

            def migration_v6(conn: Connection) -> None:
                # 升级 6: SQL 查询耗时明细监控统计（建立连接、安全卫士拦截、数据库执行、结果获取、序列化）
                cols = {
                    "connect_ms": "INTEGER",
                    "guardrail_ms": "INTEGER",
                    "execute_ms": "INTEGER",
                    "fetch_ms": "INTEGER",
                    "serialize_ms": "INTEGER",
                }
                for col_name, col_type in cols.items():
                    if not has_column(conn, "query_history", col_name):
                        conn.execute(text(f"ALTER TABLE query_history ADD COLUMN {col_name} {col_type}"))

            def migration_v7(conn: Connection) -> None:
                # 升级 7: 建立项目/工作区 (projects) 模型，支持多工作区物理隔离隔离
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS projects (
                        id VARCHAR PRIMARY KEY,
                        name VARCHAR NOT NULL,
                        description TEXT,
                        status VARCHAR NOT NULL DEFAULT 'active',
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_projects_status
                    ON projects (status)
                """))
                # 默认写入一个初始化的默认工作区，防止老数据因丢失外键而查询落空
                conn.execute(text("""
                    INSERT OR IGNORE INTO projects (
                        id,
                        name,
                        description,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'default-project',
                        'Default Workspace',
                        'Auto-created workspace for existing DataBox assets.',
                        'active',
                        datetime('now'),
                        datetime('now')
                    )
                """))

                if not has_column(conn, "data_sources", "project_id"):
                    conn.execute(text("ALTER TABLE data_sources ADD COLUMN project_id VARCHAR"))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_data_sources_project_id
                        ON data_sources (project_id)
                    """))

                # 将已有老旧数据源一律划归给默认工作区下
                conn.execute(text("""
                    UPDATE data_sources
                    SET project_id = 'default-project'
                    WHERE project_id IS NULL OR project_id = ''
                """))

            def migration_v8(conn: Connection) -> None:
                # 升级 8: 建立本地开发虚拟数据库环境 (database_environments) 核心参数表
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS database_environments (
                        id VARCHAR PRIMARY KEY,
                        project_id VARCHAR NOT NULL,
                        name VARCHAR NOT NULL,
                        runtime VARCHAR NOT NULL DEFAULT 'docker',
                        engine_type VARCHAR NOT NULL DEFAULT 'mysql',
                        engine_version VARCHAR NOT NULL DEFAULT '8.0',
                        image VARCHAR NOT NULL DEFAULT 'mysql:8.0',
                        container_name VARCHAR NOT NULL,
                        host VARCHAR NOT NULL DEFAULT '127.0.0.1',
                        port INTEGER NOT NULL,
                        database_name VARCHAR NOT NULL,
                        username VARCHAR NOT NULL,
                        password_ciphertext VARCHAR NOT NULL,
                        password_nonce VARCHAR NOT NULL,
                        datasource_id VARCHAR,
                        status VARCHAR NOT NULL DEFAULT 'created',
                        last_health_status VARCHAR,
                        last_health_at DATETIME,
                        last_error TEXT,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_database_environments_project
                    ON database_environments (project_id)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_database_environments_status
                    ON database_environments (status)
                """))
                if not has_column(conn, "data_sources", "environment_id"):
                    conn.execute(text("ALTER TABLE data_sources ADD COLUMN environment_id VARCHAR"))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_data_sources_environment_id
                        ON data_sources (environment_id)
                    """))

            def migration_v9(conn: Connection) -> None:
                # 升级 9: 建立物理备份与恢复还原日志清单表 (backup_records)
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS backup_records (
                        id VARCHAR PRIMARY KEY,
                        project_id VARCHAR NOT NULL,
                        datasource_id VARCHAR NOT NULL,
                        environment_id VARCHAR,
                        label VARCHAR,
                        backup_type VARCHAR NOT NULL DEFAULT 'mysqldump',
                        status VARCHAR NOT NULL DEFAULT 'running',
                        file_path TEXT,
                        file_size_bytes INTEGER,
                        checksum_sha256 VARCHAR,
                        started_at DATETIME NOT NULL,
                        completed_at DATETIME,
                        duration_ms INTEGER,
                        error_message TEXT,
                        created_at DATETIME NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_backup_records_project
                    ON backup_records (project_id)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_backup_records_datasource
                    ON backup_records (datasource_id)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_backup_records_created
                    ON backup_records (created_at)
                """))

            def migration_v10(conn: Connection) -> None:
                # 升级 10: 建立智能表结构图形化设计草稿清单表 (table_design_drafts)
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS table_design_drafts (
                        id VARCHAR PRIMARY KEY,
                        project_id VARCHAR NOT NULL,
                        table_name VARCHAR NOT NULL,
                        table_comment VARCHAR,
                        columns_json TEXT NOT NULL,
                        indexes_json TEXT NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_table_design_drafts_project
                    ON table_design_drafts (project_id)
                """))

            migrations = {
                1: migration_v1,
                2: migration_v2,
                3: migration_v3,
                4: migration_v4,
                5: migration_v5,
                6: migration_v6,
                7: migration_v7,
                8: migration_v8,
                9: migration_v9,
                10: migration_v10,
            }

            # 串行递增应用迁移
            with engine.begin() as conn:
                res = conn.execute(text("SELECT version FROM schema_migrations"))
                applied_versions = {row[0] for row in res.fetchall()}

                for version in sorted(migrations.keys()):
                    if version not in applied_versions:
                        print(f"正在手动执行老旧 SQLite 表结构迁移版本 v{version}...")
                        migrations[version](conn)
                        conn.execute(
                            text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, datetime('now'))"),
                            {"v": version}
                        )
                        print(f"老旧 SQLite 表结构迁移版本 v{version} 成功应用。")

            # 5. 【平滑交接核心】使用 Alembic 的 `stamp` 命令，手动将当前的物理表结构状态与 Alembic 的第一个基线版本 '99b4fdab0781' 对齐打桩！
            # 这样，Alembic 就会知道当前数据库已经是 v10 结构，无需重复建表，未来只需用 Alembic 继续升级新字段即可。
            print("开始打桩！标记基线版本为 Alembic 基准版本 ID '99b4fdab0781'...")
            command.stamp(alembic_cfg, "99b4fdab0781")

            # 6. 删除以前老旧无用的临时记录表，完美完成新旧机制交接！
            print("删除老旧的过渡状态 schema_migrations 临时表...")
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE schema_migrations"))

            print("恭喜：手写数据库表结构成功平滑地向 Alembic 版本系统完成交接！")

        # ---------------------------------------------------------------------
        # 情景二：正常状态，直接使用 Alembic 一键升级（upgrade head）至最新代码版本
        # ---------------------------------------------------------------------
        print("正在安全执行 Alembic 元数据库更新至最新表结构(Head)...")
        command.upgrade(alembic_cfg, "head")
        print("所有元数据库表结构及索引成功通过 Alembic 完成初始化与校准。")

    except Exception as exc:
        print(f"❌ 元数据库表结构版本迁移严重失败: {exc}")
        # ---------------------------------------------------------------------
        # 7. 物理容灾自动回滚机制 (Disaster Recovery Restore)
        # ---------------------------------------------------------------------
        if backup_path and backup_path.exists():
            print(f"🔄 系统触发自动容灾机制：断开所有元数据库连接，并从升级前物理备份 '{backup_path.name}' 中还原数据库...")
            try:
                engine.dispose()  # 断开当前物理引擎中所有的活跃连接池，解除文件占用锁
                shutil.copy2(backup_path, DB_PATH)  # 物理覆盖还原
                print("🔄 容灾成功：元数据库已恢复至升级前完好无损的快照状态。")
            except Exception as restore_err:
                print(f"🚨 致命危险：在恢复还原旧元数据时发生了更严重的错误: {restore_err}")
        raise exc

