import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from sqlite_archive.logic import (
    SqlitePathImpl,
    _filename,
    _qident,
    is_sqlite,
    on_file_open,
    open_action,
)


class _Pane:
    def __init__(self, focused=None):
        self.focused = focused
        self.path = "C:/data"

    def cd(self, path):
        self.path = path


class _Context:
    def __init__(self, focused=None):
        self.pane = _Pane(focused)


class _Entry:
    def __init__(self, path, is_dir=False):
        self.path = path
        self.is_dir = is_dir


def _database(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute('CREATE TABLE "items" (id INTEGER, value TEXT)')
        connection.execute("INSERT INTO items VALUES (1, 'hello')")
        connection.execute('CREATE TABLE "bad/name" (value BLOB)')
        connection.execute("INSERT INTO \"bad/name\" VALUES (X'0102')")
        connection.commit()
    finally:
        connection.close()


def _uri(path):
    database = quote(path.as_posix(), safe="/:")
    return f"sqlite://{database}#"


class SqliteArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)

    def test_quotes_sqlite_identifiers(self):
        self.assertEqual(_qident('a"b'), '"a""b"')

    def test_sanitizes_virtual_file_names(self):
        self.assertEqual(_filename("bad/name"), "bad_name")

    def test_read_only_backend_lists_schema_and_csv(self):
        database = self.directory / "archive.sqlite"
        _database(database)
        before = database.read_bytes()

        root = SqlitePathImpl(_uri(database))
        children = {entry.name: entry for entry in root.iterdir()}

        self.assertTrue(root.is_dir())
        self.assertEqual(set(children), {"schema.sql", "items.csv", "bad_name.csv"})
        self.assertIn("CREATE TABLE", children["schema.sql"].read_text())
        self.assertEqual(children["items.csv"].read_text(), "id,value\n1,hello\n")
        self.assertEqual(
            children["bad_name.csv"].read_text(), "value\n<BLOB 2 bytes>\n")
        self.assertEqual(database.read_bytes(), before)

        with self.assertRaises(OSError):
            root.write_bytes(b"not allowed")

    def test_open_action_and_file_hook_only_claim_sqlite_files(self):
        database = self.directory / "archive.db"
        _database(database)
        ordinary_db = self.directory / "ordinary.db"
        ordinary_db.write_bytes(b"not a SQLite database")
        ctx = _Context(_Entry(database))

        open_action(ctx)
        self.assertEqual(ctx.pane.path, _uri(database.resolve()))

        ctx.pane.path = "C:/data"
        event = type("Event", (), {"path": ordinary_db})()
        self.assertFalse(on_file_open(ctx, event))
        self.assertEqual(ctx.pane.path, "C:/data")
        self.assertFalse(is_sqlite(ordinary_db))

    def test_open_action_ignores_directories_and_non_sqlite_files(self):
        ordinary_db = self.directory / "ordinary.db"
        ordinary_db.write_bytes(b"not a SQLite database")
        ctx = _Context(_Entry(ordinary_db))

        open_action(ctx)
        self.assertEqual(ctx.pane.path, "C:/data")

        ctx.pane.focused = _Entry(ordinary_db, is_dir=True)
        open_action(ctx)
        self.assertEqual(ctx.pane.path, "C:/data")

    def test_database_uri_escapes_special_characters(self):
        database = self.directory / "archive #1.sqlite"
        _database(database)

        root = SqlitePathImpl(_uri(database))
        self.assertTrue(root.is_dir())
        self.assertTrue(root.root_prefix().endswith("archive%20%231.sqlite#"))


if __name__ == "__main__":
    unittest.main()
