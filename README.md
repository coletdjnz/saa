# Stream Auto Archiver
Automatically archive streams as they come online, splitting them into chunks.

Uses Streamlink to download the streams. 

**NOTE: This is still under early development, and major changes are likely to occur.**

## Installation

Requires Python 3.8+ (This is going to be designed to use in a Docker container anyways)
Clone this repository:

    git clone https://gitlab.com/colethedj/stream_auto_archiver.git && cd stream_auto_archiver

(Optional, but recommended) - Create Python virtual environment:

    python3 -m venv saa && source saa/bin/activate

Install Dependencies:
    
    pip3 install -r requirements.txt

## Usage
 
**Configure config.yml**

In this file is where you can configure all the streams/streamers/channels to archive. 
The sites that are supported depends on Streamlink. 

(Optional) `streamlink_args` are any extra arguments you wish to pass to Streamlink.  

Example:
```yaml
TwitchStream:
  url: "https://twitch.tv/channel"
  name: "TwitchStream"
  split_time: 3600
  download_directory: "~/Downloads"
  streamlink_args:
    - "--twitch-disable-hosting"
```

For now the way to run this is simply

    python3 stream_auto_archiver/run.py


## TODO

View TODO.md