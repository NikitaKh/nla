import argparse
import gzip
import json
import os
import re
import shutil
import signal
import sys
import traceback
from collections import defaultdict
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from statistics import median
from typing import Any, Dict, List

import structlog

from nla.utils.log_config import configure_struct_logger

logger = structlog.get_logger()

LOG_FILE_REGEX = re.compile(r"nginx-access-ui\.log-(\d{8})(\.gz)?$")

LOG_LINE_REGEX = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+(?:\S+)?\s+\s*(?P<timestamp>.+) "(?P<method>\w+) '
    r'(?P<url>.+?) HTTP\/.+?"\s+\d+\s+\d+\s+".*"\s+"[^"]+"\s+"[^"]+"\s+"[^"]+'
    r'"\s+"[^"]+"\s+(?P<request_time>\d+\.\d+)$'
)


def load_config_file(basic_config: Dict[str, Any], path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        logger.error(f"Conf file not exist: " f"{path}", exc_info=True, stack_info=True)
        raise FileNotFoundError
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            try:
                config_file = json.loads(content) if content else json.loads("{}")
                config = basic_config.copy()
                config.update(config_file)
            except JSONDecodeError as decode_error:
                logger.error(
                    f"Error while parsing conf file {path}: {decode_error}",
                    exc_info=True,
                    stack_info=True,
                )
                raise
    except Exception as e:
        logger.error(f"Error while reading conf file {path}: {e}", exc_info=True, stack_info=True)
        raise
    else:
        logger.info(f"Config loaded successfully: {config}")
        return config


def find_latest_log_file(log_dir: Path) -> str | None:
    latest = None
    try:
        for entry in os.listdir(log_dir):
            match = LOG_FILE_REGEX.match(entry)
            if match:
                date_str = match.group(1)
                date = datetime.strptime(date_str, "%Y%m%d")
                full_path = os.path.join(log_dir, entry)
                if not latest or date > latest[0]:
                    latest = (date, full_path)
    except Exception as e:
        logger.error(
            f"Error while finding log dir {log_dir}: {e}",
            exc_info=True,
            stack_info=True,
        )
        raise
    else:
        return latest[1] if latest else None


def parse_log_file(filepath: str, report_size: int) -> list[dict[str, float | int | str | Any]]:
    total_count = 0
    total_time = 0.0
    url_stats = defaultdict(list)

    open_func = gzip.open if filepath.endswith(".gz") else open

    try:
        with open_func(filepath, "rt", encoding="utf-8") as f:
            for line in f:
                match = LOG_LINE_REGEX.match(line)
                if not match:
                    continue

                url = match.group("url")
                try:
                    request_time = float(match.group("request_time"))
                except ValueError:
                    continue

                url_stats[url].append(request_time)
                total_count += 1
                total_time += request_time

        stats = []
        for url, times in url_stats.items():
            count = len(times)
            time_sum = sum(times)
            stats.append(
                {
                    "url": url,
                    "count": count,
                    "count_perc": round(count / total_count * 100, 3),
                    "time_sum": round(time_sum, 3),
                    "time_perc": round(time_sum / total_time * 100, 3),
                    "time_avg": round(time_sum / count, 3),
                    "time_max": round(max(times), 3),
                    "time_med": round(median(times), 3),
                }
            )

        stats.sort(key=lambda x: x["time_sum"], reverse=True)

        return stats[:report_size]
    except Exception as e:
        logger.error(
            f"Error while parsing log file {filepath}: {e}",
            exc_info=True,
            stack_info=True,
        )
        raise


def render_report(report_data: List[Any], report_dir: Path, report_date: str, resources_dir: Path) -> None:
    os.makedirs(report_dir, exist_ok=True)
    report_filename = f"report-{report_date}.html"
    report_path = os.path.join(report_dir, report_filename)

    try:
        with open(f"{resources_dir}/report.html", "r", encoding="utf-8") as template_file:
            template = template_file.read()

        json_data = json.dumps(report_data, ensure_ascii=False)
        report_content = template.replace("$table_json", json_data)

        with open(report_path, "w", encoding="utf-8") as output_file:
            output_file.write(report_content)

        logger.info(f"Report created: {report_path}")
        return
    except Exception as e:
        logger.error(f"Error while creating report: {e}", exc_info=True, stack_info=True)
        raise


def copy_jc_function(resources_dir: Path, report_dir: Path) -> None:
    try:
        src = f"{resources_dir}/jquery.tablesorter.min.js"
        dst = f"{report_dir}/jquery.tablesorter.min.js"
        shutil.copyfile(src, dst)
    except Exception as e:
        logger.error(f"Error while copying js file: {e}", exc_info=True, stack_info=True)


def global_exception_handler(exc_type: Any, exc_value: Any, exc_traceback: Any) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        logger.error("Interrupted by user", exc_info=True)
        return
    logger.error(
        "Unhandled exception",
        exc_type=str(exc_type),
        exc_value=str(exc_value),
        traceback="".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
    )


def handle_sigterm(signum: Any, frame: Any) -> None:
    logger.warning("Received SIGTERM, shutting down")
    sys.exit(143)


def main() -> None:
    # default config
    config = {
        "REPORT_SIZE": 10,
        "REPORT_DIR": "../reports",
        "LOG_DIR": "../log",
        "DATA_DIR": "../data",
        "STRUCT_LOG_FILE": "../app.log",
    }

    parent_path = Path(__file__).parent

    conf_path: Path = parent_path / "../data/config"
    report_dir: Path = parent_path / str(config.get("REPORT_DIR"))
    log_dir: Path = parent_path / str(config.get("LOG_DIR"))
    data_dir: Path = parent_path / str(config.get("DATA_DIR"))
    log_file: Path = parent_path / str(config.get("STRUCT_LOG_FILE"))

    # prepare custom config data
    parser = argparse.ArgumentParser(description="NLA (Nginx Log Parser)")
    parser.add_argument("--config", type=str, default=conf_path, help="Path to config file")
    args = parser.parse_args()
    config = load_config_file(basic_config=config, path=args.config)

    global logger
    logger = configure_struct_logger(log_file)

    # define latest log file
    latest_log_file = find_latest_log_file(log_dir)
    if not latest_log_file:
        logger.info("Log dir is empty.")
        return
    logger.info(f"Log file loaded successfully: {latest_log_file}")

    # extracting log date
    log_file_date_match = re.search(r"(\d{8})", latest_log_file)
    log_file_date = log_file_date_match.group(1) if log_file_date_match else None
    if log_file_date is None:
        logger.error("Could not extract date from log file name.")
        return
    log_file_date_converted = datetime.strptime(log_file_date, "%Y%m%d").strftime("%Y.%m.%d")

    # check whether repost exists
    report_path = Path(report_dir) / f"report-{log_file_date_converted}.html"
    if report_path.exists():
        logger.info(f"Report already exists: {report_path}")
        return

    # prepare report
    report_size = config.get("REPORT_SIZE")
    if not isinstance(report_size, int):
        logger.error(f"Invalid REPORT_SIZE in config: {report_size}")
        return
    report_data = parse_log_file(latest_log_file, report_size)
    render_report(report_data, report_dir, log_file_date_converted, data_dir)
    copy_jc_function(data_dir, report_dir)


if __name__ == "__main__":
    sys.excepthook = global_exception_handler
    signal.signal(signal.SIGTERM, handle_sigterm)
    main()
