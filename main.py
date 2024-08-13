import datetime
import json
import os
import sys
import time

import pytz
import requests
import schedule

# https://discordapp.com/developers/docs/resources/webhook#execute-webhook
# https://discordapp.com/developers/docs/resources/channel#embed-object


def timestamp() -> str:
    timestamp = datetime.datetime.now()
    tz = pytz.timezone(os.environ['TZ'])
    timestamp = timestamp.astimezone(tz)
    return timestamp.strftime('%x %X')


def webhook(content: str):
    print(timestamp(), '[INFO]', content)
    url = os.environ['WEBHOOK_URL']
    if len(url) > 0:
        data = {"content": content}  # "username" : ""
        # data["embeds"] = [{"description" : "", "title" : ""}]
        result = requests.post(url, json=data)
        try:
            result.raise_for_status()
        except requests.exceptions.HTTPError as error:
            print(timestamp(), '[ERROR]', error, file=sys.stderr)
        else:
            print(timestamp(), '[INFO] Status Code', result.status_code)


def gallery_dl():
    with open('gallery-dl/config.json') as config_f:
        config = json.load(config_f)
    for url in config:
        path, users = config[url]
        for user_id in users:
            args = ' '.join(users[user_id])
            count_i = count_f = 0
            if os.path.exists(f'/downloads/{path}/{user_id}'):
                count_i = len(
                    [x for x in os.listdir(f'/downloads/{path}/{user_id}') if os.path.isfile(x)]
                )
            os.system(f'gallery-dl {url}{user_id} -d /downloads {args}')
            if os.path.exists(f'/downloads/{path}/{user_id}'):
                count_f = len(
                    [x for x in os.listdir(f'/downloads/{path}/{user_id}') if os.path.isfile(x)]
                )
            count_diff = '' if count_i == count_f == 0 else str(count_f - count_i) + ' '
            webhook(f'gallery-dl finished downloading {count_diff}image(s) from {path}/{user_id}.')


def main():
    print(timestamp(), '[INFO] gallery-dl Started.')
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
