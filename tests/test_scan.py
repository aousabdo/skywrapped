import struct

from helpers import bytes_read_during, grow_sparse, put, reads_during

from skywrapped.scan import scan_paths


def test_scan_skips_appledouble_and_hidden(tmp_path, fixture):
    put(tmp_path / "Light_a.fit", fixture("asiair_2600air")); put(tmp_path / "._Light_a.fit", b"\0" * 4096)
    put(tmp_path / ".DS_Store", b"x")
    frames, sk = scan_paths([str(tmp_path)], []); assert len(frames) == 1 and sk["metadata_file"] == 1


def test_scan_corrupt(tmp_path):
    put(tmp_path / "empty.fit", b""); put(tmp_path / "junk.fits", b"GIF89a" + b"\0" * 5000)
    frames, sk = scan_paths([str(tmp_path)], []); assert frames == [] and sk["unreadable"] == 2


def test_scan_excludes(tmp_path, fixture):
    put(tmp_path / "_rejected/Light_a.fit", fixture("asiair_2600air"))
    frames, sk = scan_paths([str(tmp_path)], ["*/_rejected/*"]); assert frames == [] and sk["excluded"] == 1


def test_reads_headers_only(tmp_path, fixture, monkeypatch):
    big = tmp_path / "Light_big.fit"; put(big, fixture("asiair_2600air")); grow_sparse(big, 50_000_000)
    assert bytes_read_during(lambda: scan_paths([str(tmp_path)], []), monkeypatch) <= 8640


def test_extensions_any_case_and_other_files_ignored(tmp_path, fixture):
    put(tmp_path / "a.FIT", fixture("asiair_2600air")); put(tmp_path / "b.txt", b"hello")
    put(tmp_path / "c.jpg", b"\xff\xd8")
    frames, sk = scan_paths([str(tmp_path)], [])
    assert len(frames) == 1 and sk["unreadable"] == 0


def test_accepts_a_single_file_path(tmp_path, fixture):
    p = tmp_path / "Light_a.fit"; put(p, fixture("asiair_2600air"))
    frames, _ = scan_paths([str(p)], []); assert len(frames) == 1


def test_progress_callback_counts(tmp_path, fixture):
    for i in range(3):
        put(tmp_path / f"Light_{i}.fit", fixture("asiair_2600air"))
    calls = []
    scan_paths([str(tmp_path)], [], on_progress=lambda done, total: calls.append((done, total)))
    assert calls[-1] == (3, 3)


def test_xisf_with_huge_declared_header_is_unreadable_and_barely_read(tmp_path, monkeypatch):
    p = tmp_path / "huge.xisf"
    put(p, b"XISF0100" + struct.pack("<I", 0xFFFFFFF0) + b"\0" * 4)
    grow_sparse(p, 6_000_000)
    out = {}

    def run():
        out["r"] = scan_paths([str(tmp_path)], [])
    returned, requested = reads_during(run, monkeypatch)
    frames, sk = out["r"]
    assert frames == [] and sk["unreadable"] == 1
    assert max(requested) <= 1_048_576 and returned <= 8640


def test_endless_fits_without_end_card_is_unreadable(tmp_path):
    put(tmp_path / "noend.fit", (b"SIMPLE  =                    T".ljust(80) + b" " * 80) * 1 + b" " * (1_200_000))
    frames, sk = scan_paths([str(tmp_path)], []); assert frames == [] and sk["unreadable"] == 1


def test_overlapping_paths_count_each_file_once(tmp_path, fixture):
    put(tmp_path / "Light_a.fit", fixture("asiair_2600air")); put(tmp_path / "sub/Light_b.fit", fixture("asiair_2600air"))
    frames, _ = scan_paths([str(tmp_path), str(tmp_path / "sub")], []); assert len(frames) == 2
    frames, _ = scan_paths([str(tmp_path), str(tmp_path / "Light_a.fit"), str(tmp_path)], []); assert len(frames) == 2


def test_relative_path_matches_absolute_excludes(tmp_path, fixture, monkeypatch):
    put(tmp_path / "_rejected/Light_a.fit", fixture("asiair_2600air"))
    monkeypatch.chdir(tmp_path)
    frames, sk = scan_paths(["."], ["*/_rejected/*"]); assert frames == [] and sk["excluded"] == 1


def test_unreadable_folder_is_counted(tmp_path, fixture):
    import os
    import pytest
    d = tmp_path / "locked"; put(d / "Light_a.fit", fixture("asiair_2600air")); os.chmod(d, 0)
    try:
        if os.access(d, os.R_OK):
            pytest.skip("cannot make a folder unreadable here")
        frames, sk = scan_paths([str(tmp_path)], [])
        assert frames == [] and sk["unreadable"] == 1
    finally:
        os.chmod(d, 0o700)


def test_a_need_that_asks_for_no_more_bytes_ends_the_read(tmp_path, fixture, monkeypatch):
    from skywrapped import scan
    put(tmp_path / "Light_a.fit", fixture("asiair_2600air"))
    monkeypatch.setattr(scan, "next_read", lambda d: len(d) - 1)   # never read(-1): that is the whole file
    frames, sk = scan_paths([str(tmp_path)], [])
    assert frames == [] and sk["unreadable"] == 1


def test_real_paths_resolved_only_for_files_that_count(tmp_path, fixture, monkeypatch):
    """realpath is slow on a big USB disk: only files that pass the extension filter are resolved."""
    import os

    from skywrapped import scan
    for i in range(3):
        put(tmp_path / f"Light_{i}.fit", fixture("asiair_2600air"))
    put(tmp_path / "._Light_0.fit", b"\0" * 4096)
    for i in range(20):
        put(tmp_path / f"previews/p_{i}.jpg", b"\xff\xd8")
        put(tmp_path / f"notes_{i}.txt", b"x")
    calls = []
    real = os.path.realpath
    monkeypatch.setattr(scan.os.path, "realpath", lambda p: calls.append(p) or real(p))
    frames, sk = scan_paths([str(tmp_path), str(tmp_path)], [])   # the same folder twice: each file once
    assert len(frames) == 3 and sk["metadata_file"] == 1
    assert len(calls) == 2 * 4
