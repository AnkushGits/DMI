from contextlib import contextmanager

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from flask import current_app, g


def _get_pool():
    pool = current_app.extensions.get("mysql_pool")
    if pool is None:
        pool = MySQLConnectionPool(
            pool_name="dm_skill_institute",
            pool_size=5,
            host=current_app.config["DB_HOST"],
            port=current_app.config["DB_PORT"],
            database=current_app.config["DB_NAME"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
        current_app.extensions["mysql_pool"] = pool
    return pool


def get_db():
    if "db_connection" not in g:
        g.db_connection = _get_pool().get_connection()
    return g.db_connection


class _ConnectionProxy:
    """Same as the real connection, with one safe change: start_transaction().

    Every request first runs a SELECT to check who is logged in. With the default
    settings that SELECT already opens a transaction, so a later start_transaction()
    fails with "Transaction already in progress". Here we finish that harmless
    read-only transaction first and then start the new one.
    """

    def __init__(self, connection):
        self._conn = connection

    def start_transaction(self, *args, **kwargs):
        if self._conn.in_transaction:
            self._conn.commit()
        return self._conn.start_transaction(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


class _CursorWithConnection:
    """Wraps a MySQL cursor so that `cursor.connection` always works.

    The fast (C) version of mysql-connector, which Windows installs by default, hides this
    attribute as `_connection`. The rest of the code uses `db.connection.commit()`, so
    without this wrapper every write (login, admin create, enquiry) crashes.
    """

    def __init__(self, raw_cursor, connection):
        self._cursor = raw_cursor
        self.connection = _ConnectionProxy(connection)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


@contextmanager
def cursor(dictionary=True):
    connection = get_db()
    db_cursor = connection.cursor(dictionary=dictionary)
    try:
        yield _CursorWithConnection(db_cursor, connection)
    finally:
        db_cursor.close()


def close_db(_error=None):
    connection = g.pop("db_connection", None)
    if connection is not None and connection.is_connected():
        connection.close()


def db_error_response(error):
    current_app.logger.exception("Database operation failed", exc_info=error)
    return {"error": "The service is temporarily unavailable."}, 503
