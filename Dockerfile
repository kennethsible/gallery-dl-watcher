FROM python:3.11-slim

RUN pip install pytz schedule gallery-dl

ENV TZ=America/New_York
ENV SCHEDULE_TIME=00:00
ENV ONCE_ON_STARTUP=false
ENV WEBHOOK_URL=

COPY main.py main.py

CMD ["python", "-u", "main.py"]
