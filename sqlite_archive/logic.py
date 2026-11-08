# -*- coding: utf-8 -*-
"""Browse SQLite databases as read-only virtual folders."""
import csv
import errno
import io
import os
import re
import sqlite3
from pathlib import Path as _P
from urllib.parse import quote, unquote

from xefm.path_base import ReadOnlyPathImpl, UriStatResult

MAX_ROWS = 2000
_MAGIC = b"SQLite format 3\x00"


def is_sqlite(path):
    try:
        with open(str(path), "rb") as f:
            return f.read(16) == _MAGIC
    except OSError:
        return False


def _cell(value):
    if isinstance(value, bytes):
        return f"<BLOB {len(value)} bytes>"
    return value


def _qident(name):
    return '"' + name.replace('"', '""') + '"'


def _filename(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name) or "_"


def _unique(used, name):
    candidate = name
    index = 2
    stem, suffix = os.path.splitext(name)
    while candidate in used:
        candidate = f"{stem} ({index}){suffix}"
        index += 1
    used.add(candidate)
    return candidate


class SqlitePathImpl(ReadOnlyPathImpl):
    """A read-only ``sqlite://<database>#<virtual path>`` backend."""

    SCHEME = "sqlite"
    READ_ONLY_MESSAGE = "SQLite archive paths are read-only"
    _cache = {}

    def parse_uri(self, uri):
        prefix = f"{self.SCHEME}://"
        if not uri.startswith(prefix):
            raise ValueError(f"not a {prefix} URI: {uri!r}")
        database, separator, key = uri[len(prefix):].partition("#")
        if not separator or not database:
            raise ValueError(f"not a SQLite archive URI: {uri!r}")
        self._database = _P(unquote(database))
        return key

    def root_prefix(self):
        database = quote(self._database.as_posix(), safe="/:")
        return f"{self.SCHEME}://{database}#"

    @property
    def parent(self):
        if self.key:
            return self.at("/".join(self._segments[:-1]))
        return self._database.parent

    def _files(self):
        try:
            info = self._database.stat()
        except OSError:
            return {}
        if not is_sqlite(self._database):
            return {}

        cache_key = str(self._database)
        signature = (info.st_mtime_ns, info.st_size)
        cached = self._cache.get(cache_key)
        if cached is not None and cached[:2] == signature:
            return cached[2]

        uri = self._database.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.text_factory = lambda value: value.decode(
                "utf-8", errors="replace")
            objects = connection.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type DESC, name"
            ).fetchall()
            files = {
                "schema.sql": "".join(
                    f"{sql};\n\n" for _kind, _name, sql in objects if sql
                ).encode("utf-8")
            }
            used = set(files)
            for kind, name, _sql in objects:
                if kind not in ("table", "view"):
                    continue
                try:
                    cursor = connection.execute(
                        f"SELECT * FROM {_qident(name)} LIMIT {MAX_ROWS}")
                    output = io.StringIO(newline="")
                    writer = csv.writer(output, lineterminator="\n")
                    writer.writerow([column[0] for column in cursor.description])
                    for row in cursor:
                        writer.writerow([_cell(value) for value in row])
                    data = output.getvalue()
                except sqlite3.Error as error:
                    data = f"error: {error}\n"
                filename = _unique(used, _filename(name) + ".csv")
                files[filename] = data.encode("utf-8")
        finally:
            connection.close()

        self._cache[cache_key] = (*signature, files)
        return files

    def exists(self):
        if not self.key:
            return is_sqlite(self._database)
        return self.key in self._files()

    def is_dir(self):
        return not self.key and self.exists()

    def iterdir(self):
        if not self.is_dir():
            raise NotADirectoryError(str(self))
        for name in self._files():
            yield self.child(name)

    def stat(self):
        try:
            modified = self._database.stat().st_mtime
        except OSError:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                    str(self)) from None
        if self.is_dir():
            return UriStatResult(mtime=modified, is_dir=True)
        data = self._files().get(self.key)
        if data is None:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                    str(self))
        return UriStatResult(size=len(data), mtime=modified)

    def open(self, mode="r", buffering=-1, encoding=None, errors=None,
             newline=None):
        if mode not in ("r", "rt", "rb"):
            raise OSError(errno.EROFS, self.READ_ONLY_MESSAGE, str(self))
        if self.is_dir():
            raise IsADirectoryError(str(self))
        data = self._files().get(self.key)
        if data is None:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                    str(self))
        stream = io.BytesIO(data)
        if mode == "rb":
            return stream
        return io.TextIOWrapper(stream, encoding=encoding, errors=errors,
                                newline=newline)


def _open_sqlite(ctx, path):
    if "://" in str(path) or not is_sqlite(path):
        return False
    database = _P(path).resolve()
    uri = f"sqlite://{quote(database.as_posix(), safe='/:')}#"
    ctx.pane.cd(uri)
    return True


def on_file_open(ctx, event):
    """Open SQLite files as virtual folders when XeFM's file-open hook fires."""
    return _open_sqlite(ctx, event.path)


def open_action(ctx):
    """Open the focused SQLite file as a read-only virtual folder."""
    entry = ctx.pane.focused
    if entry is None or entry.is_dir:
        return
    _open_sqlite(ctx, entry.path)


SQLITE_SCHEME = {"class": SqlitePathImpl, "override": True}
