"""Flask-Migrate 环境（Alembic env.py），v3.11.0 接入。

标准 Flask-Migrate 模板：从 `current_app.extensions["migrate"].db` 取元数据，
对 SQLite 开启 `render_as_batch=True` 以支持 ALTER（SQLite 原生不支持），
未来 `flask db migrate` 自动生成的迁移脚本才能正确产出批次改写语句。

本文件随后端包（myblog/migrations/）一同部署，与 `app.py` 中
`Migrate(app, db, directory=...)` 的显式目录保持一致，故无论从哪个 cwd 运行
`flask db` 都能定位到本目录。
"""
import logging
from logging.config import fileConfig

from flask import current_app
from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def get_engine():
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions["migrate"].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions["migrate"].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            "%", "%%"
        )
    except AttributeError:
        return str(get_engine().url).replace("%", "%%")


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
config.set_main_option("sqlalchemy.url", get_engine_url())
target_db = current_app.extensions["migrate"].db


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_metadata():
    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=get_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    conf_args = current_app.extensions["migrate"].configure_args
    # SQLite 原生不支持 ALTER，开启批次改写（幂等，覆盖 Flask-Migrate 默认值）。
    conf_args["render_as_batch"] = True
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
