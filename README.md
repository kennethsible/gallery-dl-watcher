# Image Gallery Watcher & Downloader
**gallery-dl-watcher** is a wrapper of [gallery-dl](https://github.com/mikf/gallery-dl) in Docker that uses the Python [schedule](https://pypi.org/project/schedule/) package to monitor image galleries for updates and automatically download any changes.
## Docker Compose (Example)
```
services:
  gallery-dl-watcher:
    build:
      network: host
      context: .
    container_name: gallery-dl-watcher
    # environment: # OPTIONAL
    #   - TZ=America/New_York
    #   - SCHEDULE_TIME=00:00
    #   - LOGGING_LEVEL=debug
    #   - ONCE_ON_STARTUP=false
    #   - WEBHOOK_URL=https://discord.com/api/webhooks/${WEBHOOK_ID}/${DISCORD_TOKEN}
    volumes:
      - ./config.json:/gallery-dl/config.json
      - ./downloads:/downloads
    restart: unless-stopped # OPTIONAL
```
## Configuration (Example)
```
{
    "https://mangadex.org/title/":
    [
        "mangadex/Dandadan",
        {
            "68112dc1-2b80-4f20-beb8-2f2a8716a430": [
                "--chapter-filter",
                "1 <= chapter <= 5",
                "-o",
                "lang=en"
            ]
        }
    ]
}
```