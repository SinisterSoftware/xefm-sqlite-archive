from sqlite_archive.logic import _qident, _filename

def test_quotes_sqlite_identifiers():
    assert _qident('a"b') == '"a""b"'

def test_sanitizes_virtual_file_names():
    assert _filename('bad/name') == 'bad_name'
