# -*- coding: utf-8 -*-
"""SQLite データベースを読み取り専用の仮想フォルダとして見せる (~/.xefm/extensions/sqlite_archive.py)

sqlite://<dbの絶対パス>#  の中身:
    schema.sql        全テーブル/ビュー/インデックスの CREATE 文
    <テーブル名>.csv   先頭 MAX_ROWS 行 (ビューも同様)。内蔵ビューアで読める

標準ライブラリの sqlite3 だけで動く。DB は mode=ro で開くので書き込まれない。

config.py:
    from sqlite_archive import SqlitePathImpl, open_sqlite
    PATH_SCHEMES = {"sqlite": {"class": SqlitePathImpl}}
.db/.sqlite などの Enter / V は external_viewer.py の EXTERNAL_VIEWERS が open_sqlite を呼ぶ。
SQLite でない .db (Thumbs.db など) は open_sqlite が False を返し、従来の扱いに戻る。
"""
import csv
import io
import re
import sqlite3
from pathlib import Path as _P

from mail_archive import EmlPathImpl, _EmlArchive

MAX_ROWS = 2000
_MAGIC = b"SQLite format 3\x00"


def is_sqlite(path):
    try:
        with open(str(path), "rb") as f:
            return f.read(16) == _MAGIC
    except OSError:
        return False


def _cell(v):
    if isinstance(v, bytes):
        return f"<BLOB {len(v)} bytes>"
    return v


def _qident(name):
    return '"' + name.replace('"', '""') + '"'


def _filename(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name) or "_"


class _SqliteArchive(_EmlArchive):
    _cache = {}

    def _parse(self):
        uri = _P(self.eml_path).resolve().as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            con.text_factory = lambda b: b.decode("utf-8", errors="replace")
            objs = con.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type DESC, name").fetchall()
            schema = "".join(f"{sql};\n\n" for _t, _n, sql in objs if sql)
            self.root_files["schema.sql"] = schema.encode("utf-8")
            used = {"schema.sql"}
            for typ, name, _sql in objs:
                if typ not in ("table", "view"):
                    continue
                try:
                    cur = con.execute(f"SELECT * FROM {_qident(name)} LIMIT {MAX_ROWS}")
                    buf = io.StringIO(newline="")
                    w = csv.writer(buf, lineterminator="\n")
                    w.writerow([d[0] for d in cur.description])
                    for row in cur:
                        w.writerow([_cell(v) for v in row])
                    data = buf.getvalue()
                except sqlite3.Error as e:
                    data = f"error: {e}\n"
                self.root_files[self._unique(used, _filename(name) + ".csv")] = data.encode("utf-8")
        finally:
            con.close()


class SqlitePathImpl(EmlPathImpl):
    """sqlite://<dbの絶対パス>#<内部パス>。構造は eml:// と同じ。"""

    SCHEME = "sqlite"
    READ_ONLY_MESSAGE = "データベースは読み取り専用です"

    def _archive(self):
        return _SqliteArchive.get(self._eml_path)


def open_sqlite(ctx, path):
    """SQLite ならフォルダとして開いて True。そうでなければ False (従来の扱いに任せる)。"""
    if "://" in str(path) or not is_sqlite(path):
        return False
    ctx.pane.cd(f"sqlite://{path.absolute()}#")
    return True


SQLITE_SCHEME = {"class": SqlitePathImpl, "override": True}
