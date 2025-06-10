import gzip
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Generator
from unittest import mock

import pytest
from pytest import MonkeyPatch

import nla.log_analyzer as analyzer
from nla.log_analyzer import (
    find_latest_log_file,
    load_config_file,
    parse_log_file,
    render_report,
)


@pytest.fixture(autouse=True)
def mock_logger(monkeypatch: MonkeyPatch) -> Generator[mock.MagicMock, None, None]:
    mock_log = mock.MagicMock()
    monkeypatch.setattr(analyzer, "logger", mock_log)
    return mock_log


@pytest.fixture
def temp_config_file() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        f.write(json.dumps({"REPORT_SIZE": 5}))
        f.flush()
        yield f.name
    os.unlink(f.name)


def test_load_config_file_success(temp_config_file):
    default_config = {"REPORT_SIZE": 10}
    config = load_config_file(default_config, temp_config_file)
    print(temp_config_file)
    assert config["REPORT_SIZE"] == 5


def test_load_config_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_config_file({}, "/non/existent/path.json")


def test_load_config_file_invalid_json() -> None:
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        f.write("{invalid_json")
        name = f.name
    with pytest.raises(json.JSONDecodeError):
        load_config_file({}, name)
    os.unlink(name)


def test_find_latest_log_file() -> Any:
    with tempfile.TemporaryDirectory() as temp_dir:
        file1 = Path(temp_dir) / "nginx-access-ui.log-20250101"
        file2 = Path(temp_dir) / "nginx-access-ui.log-20251231.gz"
        file1.touch()
        file2.touch()

        latest = find_latest_log_file(Path(temp_dir))
        assert latest is not None
        assert latest.endswith("nginx-access-ui.log-20251231.gz")


def _write_log_file(path: Path, lines: list[str], gz: bool = False) -> None:
    open_func = gzip.open if gz else open
    with open_func(path, "wt", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def test_parse_log_file_plain() -> None:
    log_line = (
        r"1.196.116.32 -  - [29/Jun/2017:03:50:22 +0300] "
        r'"GET /api/v2/banner/25019354 HTTP/1.1" 200 927 "-" '
        r'"Lynx/2.8.8dev.9 libwww-FM/2.14 SSL-MM/1.4.1 '
        r'GNUTLS/2.10.5" "-" "1498697422-2190034393-4708-9752759"'
        r' "dc7161be3" 0.390'
    )
    with tempfile.NamedTemporaryFile(mode="wt", delete=False) as f:
        f.write(log_line + "\n")
        name = f.name

    result = parse_log_file(name, report_size=1)
    assert len(result) == 1
    assert result[0]["url"] == "/api/v2/banner/25019354"
    os.unlink(name)


def test_parse_log_file_gz() -> None:
    log_line = (
        r"1.196.116.32 -  - [29/Jun/2017:03:50:22 +0300] "
        r'"GET /api/v2/banner/25019354 HTTP/1.1" 200 927 "-" '
        r'"Lynx/2.8.8dev.9 libwww-FM/2.14 SSL-MM/1.4.1 '
        r'GNUTLS/2.10.5" "-" "1498697422-2190034393-4708-9752759"'
        r' "dc7161be3" 0.390'
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".gz") as f:
        gz_path = f.name
    _write_log_file(Path(gz_path), [log_line], gz=True)

    result = parse_log_file(gz_path, report_size=1)
    assert len(result) == 1
    assert result[0]["url"] == "/api/v2/banner/25019354"
    os.unlink(gz_path)


def test_render_report(tmp_path: Path) -> Any:
    report_data = [
        {
            "url": "/example",
            "count": 1,
            "count_perc": 100.0,
            "time_sum": 1.23,
            "time_perc": 100.0,
            "time_avg": 1.23,
            "time_max": 1.23,
            "time_med": 1.23,
        }
    ]
    resources_dir = tmp_path / "resources"
    report_dir = tmp_path / "report"
    resources_dir.mkdir()
    report_dir.mkdir()

    template_path = resources_dir / "report.html"
    template_data = "<html><body>$table_json</body></html>"
    template_path.write_text(template_data, encoding="utf-8")

    render_report(report_data, report_dir, "2025.06.08", resources_dir)

    report_file = report_dir / "report-2025.06.08.html"
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "/example" in content
