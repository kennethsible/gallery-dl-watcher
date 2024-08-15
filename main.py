import json
import logging
import os
import subprocess
import time

import pytz
import requests
import schedule


def webhook(message: str, gallery: str):
    # https://discordapp.com/developers/docs/resources/webhook#execute-webhook
    # https://discordapp.com/developers/docs/resources/channel#embed-object
    url = os.environ['WEBHOOK_URL']
    if len(url) > 0:
        message += f' from **{gallery}**.'
        data = {"embeds": [{"description": message.lower(), "color": 1146986}]}
        result = requests.post(url, json=data)
        try:
            result.raise_for_status()
        except requests.exceptions.HTTPError as http_error:
            logging.error(http_error)


def gallery_dl():
    with open('gallery-dl/config.json') as config_f:
        config = json.load(config_f)
    logging.info('Monitoring Session Started')
    for url in config:
        root_path, galleries = config[url]
        for gallery_id in galleries:
            count_i = 0
            if os.path.exists(f'/downloads/{root_path}/{gallery_id}'):
                count_i = len(os.listdir(f'/downloads/{root_path}/{gallery_id}'))
            elif os.path.exists(f'/downloads/{root_path}'):
                count_i = len(os.listdir(f'/downloads/{root_path}'))
            cmd = f'gallery-dl {url}{gallery_id} -d /downloads {" ".join(galleries[gallery_id])}'
            logging.info(f'Running `{cmd}`')
            result = subprocess.run(cmd.split(), capture_output=True, text=True)
            if result.stdout:
                for output in result.stdout.strip().split('\n'):
                    logging.debug(output)
            if result.stderr:
                for output in result.stderr.strip().split('\n'):
                    logging.error(output)
            count_f = 0
            if os.path.exists(f'/downloads/{root_path}/{gallery_id}'):
                count_f = len(os.listdir(f'/downloads/{root_path}/{gallery_id}'))
                downloaded = count_f - count_i
                suffix = 's' if downloaded != 1 else ''
                message = f'{downloaded} Image{suffix} Downloaded'
            elif os.path.exists(f'/downloads/{root_path}'):
                count_f = len(os.listdir(f'/downloads/{root_path}'))
                downloaded = count_f - count_i
                suffix = 's' if downloaded != 1 else ''
                message = f'{downloaded} Collection{suffix} Downloaded'
            gallery = f'{root_path}/{gallery_id}'
            logging.info(f'{message} from {gallery}')
            if downloaded > 0:
                webhook(message, gallery)
    logging.info('Monitoring Session Finished')


def main():
    logging.basicConfig(format='[%(levelname)s] %(message)s')
    logger = logging.getLogger()
    match os.environ['LOGGING_LEVEL']:
        case 'debug':
            logger.setLevel(logging.DEBUG)
        case 'info':
            logger.setLevel(logging.INFO)
        case 'warning':
            logger.setLevel(logging.WARNING)
        case 'error':
            logger.setLevel(logging.ERROR)
        case 'critical':
            logger.setLevel(logging.CRITICAL)
    logging.info('Application Initialized')
    logging.info('Logging Level Set to ' + os.environ['LOGGING_LEVEL'])
    schedule_time = os.environ['SCHEDULE_TIME']
    if schedule_time:
        logging.info('Monitoring Scheduled for ' + os.environ['SCHEDULE_TIME'])
    if os.environ['ONCE_ON_STARTUP'] == 'true':
        gallery_dl()
    if schedule_time:
        tz = pytz.timezone(os.environ['TZ'])
        schedule.every().day.at(schedule_time, tz).do(gallery_dl)
        while True:
            schedule.run_pending()
            time.sleep(1)


if __name__ == '__main__':
    main()
