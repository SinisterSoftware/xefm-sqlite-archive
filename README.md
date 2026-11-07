# SQLite Archive

XeFM extension to browse SQLite databases read-only as virtual folders.

Install with `xefm ext install github:SinisterSoftware/xefm-sqlite-archive`.

After installation, press **Enter** on a SQLite database to browse it. The
extension checks the file's SQLite header, so non-SQLite `.db` files keep
XeFM's normal open behavior. Each database opens as a virtual folder containing
`schema.sql` and one CSV file per table or view. CSV exports contain at most
2,000 rows, and database and virtual-folder paths are read-only.

The virtual folder can also be opened directly with its `sqlite://` URI. For
example:

```text
sqlite:///home/alice/data.sqlite#
sqlite://C:/Users/Alice/data.sqlite#
```

The database path may be URL-escaped when it contains URI-special characters.
The `#` marks the root of the virtual folder. The `sqlite_archive.open` action
opens the focused SQLite file; extensions such as External Viewers can check
for it with `ctx.action_names()` and invoke it with `ctx.invoke()` instead of
importing this extension.

For development, run `xefm ext check .` and
`python -m unittest discover -s tests`.
