import argparse
import gzip
import json
import logging
import os
import re
import sys
import shutil
from collections import defaultdict
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from statistics import median

# log_format ui_short '$remote_addr  $remote_user $http_x_real_ip [$time_local] "$request" '
#                     '$status $body_bytes_sent "$http_referer" '
#                     '"$http_user_agent" "$http_x_forwarded_for" "$http_X_REQUEST_ID" "$http_X_RB_USER" '
#                     '$request_time';

LOG_FILE_REGEX = re.compile(r"nginx-access-ui\.log-(\d{8})(\.gz)?$")

LOG_LINE_REGEX = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+(?:\S+)?\s+\s*(?P<timestamp>.+) "(?P<method>\w+) (?P<url>.+?) HTTP\/.+?"\s+\d+\s+\d+\s+".*"\s+"[^"]+"\s+"[^"]+"\s+"[^"]+"\s+"[^"]+"\s+(?P<request_time>\d+\.\d+)$')


def load_config_file(basic_config: dict, path: str) -> dict:
    if not os.path.exists(path):
        logging.error(f"Conf file not exist: {path}")
        sys.exit(1)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            try:
                config_file = json.loads(content) if content else json.loads('{}')
                config = basic_config.copy()
                config.update(config_file)
                return config
            except JSONDecodeError as decode_error:
                logging.exception(f"Error while parsing conf file {path}: {decode_error}")
                sys.exit(1)
    except Exception as e:
        logging.exception(f"Error while reading conf file {path}: {e}")
        sys.exit(1)


def find_latest_log_file(log_dir: str) -> str | None:
    latest = None
    for entry in os.listdir(log_dir):
        match = LOG_FILE_REGEX.match(entry)
        if match:
            date_str = match.group(1)
            date = datetime.strptime(date_str, "%Y%m%d")
            full_path = os.path.join(log_dir, entry)
            if not latest or date > latest[0]:
                latest = (date, full_path)
    return latest[1] if latest else None


def parse_log_file(filepath: str, report_size: int) -> list:
    total_count = 0
    total_time = 0.0
    url_stats = defaultdict(list)

    open_func = gzip.open if filepath.endswith('.gz') else open

    try:
        with open_func(filepath, 'rt', encoding='utf-8') as f:
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
            stats.append({
                "url": url,
                "count": count,
                "count_perc": round(count / total_count * 100, 3),
                "time_sum": round(time_sum, 3),
                "time_perc": round(time_sum / total_time * 100, 3),
                "time_avg": round(time_sum / count, 3),
                "time_max": round(max(times), 3),
                "time_med": round(median(times), 3),
            })

        stats.sort(key=lambda x: x["time_sum"], reverse=True)

        return stats[:report_size]
    except Exception as e:
        logging.exception(f"Error while parsing log file {filepath}: {e}")
        sys.exit(1)


def render_report(report_data: list, report_dir: str, report_date: str, resources_dir: str):
    os.makedirs(report_dir, exist_ok=True)
    report_filename = f"report-{report_date}.html"
    report_path = os.path.join(report_dir, report_filename)

    src = f'{resources_dir}/jquery.tablesorter.min.js'
    dst = f'{report_dir}/jquery.tablesorter.min.js'

    try:
        with open(f'{resources_dir}/report.html', 'r', encoding='utf-8') as template_file:
            template = template_file.read()

        json_data = json.dumps(report_data, ensure_ascii=False)
        report_content = template.replace('$table_json', json_data)

        with open(report_path, 'w', encoding='utf-8') as output_file:
            output_file.write(report_content)

        logging.info(f"Report created: {report_path}")
    except Exception as e:
        logging.error(f"Error while creating report: {e}")
        raise

def copy_jc_function(resources_dir: str, report_dir: str):
    try:
        src = f'{resources_dir}/jquery.tablesorter.min.js'
        dst = f'{report_dir}/jquery.tablesorter.min.js'
        shutil.copyfile(src, dst)
    except Exception as e:
        logging.error(f"Error while copying js file: {e}")


def main():
    config = {
        "REPORT_SIZE": 10,
        "REPORT_DIR": "./reports",
        "LOG_DIR": "./log",
        "RESOURCES_DIR": "./resources"
    }
    conf_path: str = './resources/config'

    parser = argparse.ArgumentParser(description="NLA (Nginx Log Parser)")
    parser.add_argument('--config', type=str, default=conf_path, help='Path to config file')
    args = parser.parse_args()
    config = load_config_file(basic_config=config, path=args.config)

    latest_log_file = find_latest_log_file(config["LOG_DIR"])
    if not latest_log_file:
        logging.info("Log dir is empty.")
        sys.exit(0)
    log_file_date = re.search(r'(\d{8})', latest_log_file).group(1)
    log_file_date_converted = datetime.strptime(log_file_date, "%Y%m%d").strftime("%Y.%m.%d")
    report_path = Path(config["REPORT_DIR"]) / f"report-{log_file_date_converted}.html"
    if report_path.exists():
        logging.info(f"Report already exists: {report_path}")
        return
    report_data = parse_log_file(latest_log_file, config["REPORT_SIZE"])
    render_report(report_data, config["REPORT_DIR"], log_file_date_converted, config["RESOURCES_DIR"])
    copy_jc_function(config["RESOURCES_DIR"], config["REPORT_DIR"])

if __name__ == '__main__':
    main()
