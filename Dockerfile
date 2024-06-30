FROM alpine:latest
MAINTAINER coletdjnz <coletdjnz@protonmail.com>

COPY . /saa

RUN apk update && \
    apk add ffmpeg \
    python3 \
    python3-dev \
    py-pip \
    ca-certificates \
    libc-dev \
    git \
    gcc && \
    pip3 install -r /saa/requirements.txt -U --break-system-packages && \
    wget https://downloads.rclone.org/rclone-current-linux-amd64.zip && \
    unzip rclone-current-linux-amd64.zip && \
    cd rclone-*-linux-amd64 && \
    cp rclone /usr/bin/ && \
    cd / && \
    rm rclone-current-linux-amd64.zip && \
    rclone --version && \
    cd /saa && \
    pip3 install . --break-system-packages && \
    cd / && \
    rm -rf /saa

VOLUME ["/download", "/config"]

CMD ["saa", "--config-file", "/config/config.yml", "--streamers-file", "/config/streamers.yml"]

