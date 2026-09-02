import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile
from importlib.metadata import version
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import FrameType
from urllib.parse import urlparse

import cron_descriptor
import rarfile
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from cron_descriptor import FormatError

from gallerywatcher import __version__

downloader_logger = logging.getLogger('downloader')
watcher_logger = logging.getLogger('watcher')

DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_APP_TOKEN = os.getenv('PUSHOVER_APP_TOKEN')
DOWNLOAD_DELAY = int(os.getenv('DOWNLOAD_DELAY', '3'))
DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', '600'))
ONCE_ON_STARTUP = os.getenv('ONCE_ON_STARTUP', 'false').lower() in ('true', '1', 't')
LOG_LEVEL_DOWNLOADER = os.getenv('LOG_LEVEL_DOWNLOADER', '')
LOG_LEVEL_WATCHER = os.getenv('LOG_LEVEL_WATCHER', '')
LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', str(5 * 1024 * 1024)))
LOG_MAX_FILES = int(os.getenv('LOG_MAX_FILES', '3'))

CRON_MACROS = {
    '@yearly': '0 0 1 1 *',
    '@annually': '0 0 1 1 *',
    '@monthly': '0 0 1 * *',
    '@weekly': '0 0 * * 0',
    '@daily': '0 0 * * *',
    '@midnight': '0 0 * * *',
    '@hourly': '0 * * * *',
}
CRON_SCHEDULE = os.getenv('CRON_SCHEDULE')

current_process: subprocess.Popen[str] | None = None


def notify_discord(message: str, gallery_name: str, webhook_url: str) -> None:
    message = f'{message} from \n**{gallery_name}**'
    data = {'embeds': [{'description': message, 'color': 1146986}]}
    result = requests.post(webhook_url, json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as e:
        watcher_logger.error(f'upstream connection error: {e}')


def notify_pushover(message: str, gallery_name: str, user_key: str, app_token: str) -> None:
    message = f'{message} from <br><b>{gallery_name}</b>'
    data = {'message': message, 'priority': -1, 'html': 1, 'token': app_token, 'user': user_key}
    result = requests.post('https://api.pushover.net/1/messages.json', json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as e:
        watcher_logger.error(f'upstream connection error: {e}')


def extract_archive(gallery_path: Path) -> int:
    image_count = 0
    for archive in gallery_path.iterdir():
        if not archive.is_file():
            continue
        if archive.suffix not in ('.zip', '.rar'):
            continue
        watcher_logger.info(f'extracting {archive.name}')

        archive_stats = archive.stat()
        archive_mtime = archive_stats.st_mtime

        image_count -= 1
        with tempfile.TemporaryDirectory() as tmp_f:
            temp_path = Path(tmp_f)
            match archive.suffix:
                case '.zip':
                    with zipfile.ZipFile(archive) as zip_f:
                        zip_f.extractall(temp_path)
                case '.rar':
                    with rarfile.RarFile(archive) as rar_f:
                        rar_f.extractall(temp_path)

            for old_path in temp_path.rglob('*'):
                new_path = gallery_path / f'{archive.stem}_{old_path.name}'

                i = 1
                while new_path.is_file():
                    unique_suffix = f'({i}){old_path.suffix}'
                    new_path = gallery_path / f'{archive.stem}_{old_path.name} {unique_suffix}'
                    i += 1

                shutil.move(old_path, new_path)
                os.utime(new_path, (archive_mtime, archive_mtime))
                image_count += 1

        archive.unlink()
    return image_count


def run_gallery_dl(args: list[str]) -> tuple[Path | None, int]:
    global current_process
    image_count = 0
    gallery_path: Path | None = None

    try:
        with subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        ) as process:
            current_process = process

            if process.stdout:
                for line in process.stdout:
                    if not (line := line.strip()):
                        continue

                    log_match = re.match(
                        r'^\[.*?\]\[(debug|info|warning|error)\]', line, re.IGNORECASE
                    )
                    if log_match:
                        match log_match.group(1).upper():
                            case 'ERROR':
                                downloader_logger.error(line)
                            case 'WARNING':
                                downloader_logger.warning(line)
                            case _:
                                downloader_logger.debug(line)
                        continue

                    if not line.startswith('#'):
                        output_path = Path(line)
                        if gallery_path is None and output_path.is_file():
                            gallery_path = output_path.parent
                        image_count += 1

            if (return_code := process.wait(timeout=DOWNLOAD_TIMEOUT)) != 0:
                downloader_logger.error(f'exited with status {return_code}')

    except subprocess.TimeoutExpired:
        downloader_logger.error(f'timed out after {DOWNLOAD_TIMEOUT}s')
        if current_process is not None:
            current_process.kill()
    except Exception as e:  # noqa: BLE001
        downloader_logger.error(f'unexpected error occurred: {e}')
    finally:
        current_process = None

    return gallery_path, image_count


def parse_domain(gallery_url: str) -> str:
    return urlparse(gallery_url).netloc.removeprefix('www.').split('.')[0]


def scan_galleries() -> None:
    with open('/config/config.json') as config_f:
        config = json.load(config_f)

    for gallery_url, galleries in config.items():
        for gallery_id, gallery_args in galleries.items():
            gallery_name = f'{parse_domain(gallery_url)}/{gallery_id}'
            watcher_logger.info(f'scanning {gallery_name}')

            args = ['gallery-dl', gallery_url + gallery_id] + gallery_args
            if '--directory' not in gallery_args:
                args.extend(['--destination', '/downloads'])
            if Path('/extractors').is_dir():
                args.extend(['--extractors', '/extractors'])
            args.extend(['--config', '/config/gallery-dl.conf'])
            gallery_path, image_count = run_gallery_dl(args)

            if gallery_path and image_count > 0:
                image_count += extract_archive(gallery_path)
                suffix = 's' if image_count > 1 else ''
                message = f'{image_count} image{suffix} downloaded'
                watcher_logger.info(f'{message} from {gallery_name}')

                if DISCORD_WEBHOOK:
                    notify_discord(message, gallery_name, DISCORD_WEBHOOK)
                if PUSHOVER_USER_KEY and PUSHOVER_APP_TOKEN:
                    notify_pushover(message, gallery_name, PUSHOVER_USER_KEY, PUSHOVER_APP_TOKEN)

                time.sleep(DOWNLOAD_DELAY)


def parse_log_level(level_str: str, default: int) -> int:
    level_mapping = logging.getLevelNamesMapping()
    return level_mapping.get(level_str.upper().strip(), default)


def main() -> None:
    log_path = Path('/config/gallery-watcher.log')
    log_path.parent.mkdir(parents=True, exist_ok=True)
    downloader_level = parse_log_level(LOG_LEVEL_DOWNLOADER, logging.ERROR)
    watcher_level = parse_log_level(LOG_LEVEL_WATCHER, logging.INFO)

    def console_filter(record: logging.LogRecord) -> bool:
        if record.name == downloader_logger.name:
            return record.levelno >= downloader_level
        if record.name == watcher_logger.name:
            return record.levelno >= watcher_level
        # return record.levelno >= logging.WARNING
        return True

    file_handler = RotatingFileHandler(
        log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_MAX_FILES, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.addFilter(console_filter)
    logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s %(levelname)s] [%(name)s] %(message)s',
        handlers=[file_handler, stream_handler],
    )
    logging.getLogger('apscheduler').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)

    watcher_logger.info(f'Gallery Watcher {__version__}-{version("gallery-dl")}')

    if ONCE_ON_STARTUP:
        scan_galleries()
    if expr := CRON_SCHEDULE:
        if expr.startswith('@'):
            macro = expr
            try:
                expr = CRON_MACROS[macro]
            except KeyError as e:
                e.add_note(f"unsupported cron macro '{macro}'")
                raise
        timezone = os.getenv('TZ', 'UTC')
        try:
            expr_desc = cron_descriptor.get_description(expr)
            expr_desc = expr_desc[0].lower() + expr_desc[1:]
            trigger = CronTrigger.from_crontab(expr, timezone)
        except (FormatError, ValueError) as e:
            e.add_note(f"unsupported cron expression '{expr}'")
            raise

        scheduler = BlockingScheduler()
        scheduler.add_job(scan_galleries, trigger)
        watcher_logger.info(f'scheduled task to run {expr_desc} ({timezone})')

        def handle_signal(signum: int, frame: FrameType | None) -> None:
            sig_name = signal.Signals(signum).name
            watcher_logger.info(f'received {sig_name} signal')
            if current_process:
                watcher_logger.info('terminating gallery-dl subprocess')
                current_process.terminate()
            scheduler.shutdown()

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        scheduler.start()


if __name__ == '__main__':
    main()
