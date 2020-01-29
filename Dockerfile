FROM alpine:latest
MAINTAINER colethedj <colethedj@protonmail.com>

COPY requirements.txt /
RUN apk update && \
    apk add ffmpeg \
    python3 \
    python3-dev \
    py-pip \
    ca-certificates \
    libc-dev \
    wget \
    gcc && \
    pip3 install -r /requirements.txt -U && \
    wget https://downloads.rclone.org/rclone-current-linux-amd64.zip && \
    unzip rclone-current-linux-amd64.zip && \
    cd rclone-*-linux-amd64 && \
    cp rclone /usr/bin/ && \
    cd / && \
    rm -rf rclone-current-linux-amd64.zip && \
    rclone --version

COPY saa /saa

VOLUME ["/download", "/config"]

CMD ["python3", "/saa/saa.py", "--config-file", "/config/config.yml", "--streamers-file", "/config/streamers.yml"]

