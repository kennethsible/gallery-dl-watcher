# import datetime
import json
import os
import sys
import time

import pytz
import requests
import schedule

# https://discordapp.com/developers/docs/resources/webhook#execute-webhook
# https://discordapp.com/developers/docs/resources/channel#embed-object


# def timestamp() -> str:
#     timestamp = datetime.datetime.now()
#     tz = pytz.timezone(os.environ['TZ'])
#     timestamp = timestamp.astimezone(tz)
#     return timestamp.strftime('%x %X')


def webhook(message: str, gallery: str):
    print(f'[INFO] {message} from {gallery}')
    url = os.environ['WEBHOOK_URL']
    if len(url) > 0:
        message += f' from **{gallery}**.'
        data = {"embeds": [{"description": message.lower(), "color": 1146986}]}
        result = requests.post(url, json=data)
        try:
            result.raise_for_status()
        except requests.exceptions.HTTPError as error:
            print('[ERROR]', error, file=sys.stderr)
        else:
            print('[INFO] Discord Webhook Sent')


def gallery_dl():
    with open('gallery-dl/config.json') as config_f:
        config = json.load(config_f)
    print('[INFO] Monitoring Session Started')
    for url in config:
        root_path, galleries = config[url]
        for gallery in galleries:
            count_i = 0
            if os.path.exists(f'/downloads/{root_path}/{gallery}'):
                count_i = len(os.listdir(f'/downloads/{root_path}/{gallery}'))
            elif os.path.exists(f'/downloads/{root_path}'):
                count_i = len(os.listdir(f'/downloads/{root_path}'))
            os.system(f'gallery-dl {url}{gallery} -d /downloads {" ".join(galleries[gallery])}')
            count_f = 0
            if os.path.exists(f'/downloads/{root_path}/{gallery}'):
                count_f = len(os.listdir(f'/downloads/{root_path}/{gallery}'))
                residual = count_f - count_i
                if residual > 0:
                    suffix = 's' if residual > 1 else ''
                    webhook(f'{residual} Image{suffix} Downloaded', f'{root_path}/{gallery}')
            elif os.path.exists(f'/downloads/{root_path}'):
                count_f = len(os.listdir(f'/downloads/{root_path}'))
                residual = count_f - count_i
                if residual > 0:
                    suffix = 's' if residual > 1 else ''
                    webhook(f'{residual} Collection{suffix} Downloaded', f'{root_path}/{gallery}')
    print('[INFO] Monitoring Session Finished')


def main():
    print('[INFO] Application Initialized')
    if os.environ['ONCE_ON_STARTUP'] == 'true':
        gallery_dl()
    schedule_time = os.environ['SCHEDULE_TIME']
    tz = pytz.timezone(os.environ['TZ'])
    schedule.every().day.at(schedule_time, tz).do(gallery_dl)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
