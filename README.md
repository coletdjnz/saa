# Stream Auto Archiver (saa)

Automatically archive livestreams.

Features:
- Watch streams until they are live
- Splits streams into chunks of X seconds
- Can enable rclone to automatically pick up completed chunks and copy/move them elsewhere
- Easy configuration of streams and config
- Ability to add/remove/edit streams in the stream config while running
- Error/crash recovery


Uses Streamlink to download the streams. 


## Installation

### Docker (recommended)

I recommended using docker as that is how I have designed this program to work, however it is possible to without.

**NOTE**: In the docker image, `config.yml`, `streamers.yml` and `rclone.conf` are to be put in `/config` (see configuration section on how to configure)




Clone this repository:

    git clone https://gitlab.com/colethedj/stream_auto_archiver.git && cd saa
    
Build the docker image
    
    docker build . -t saa
  
and to run

    docker run -d --name saa -v /path/to/config:/config -v /path/to/download/location:/download --restart unless-stopped saa



**or you can use docker-compose**
(see docker-compose.yml in repository)


```yaml
version: "3.5"
services:
  saa:
    build:
      context: .
    container_name: saa
    volumes:
     - /path/to/config:/config
     - /path/to/download/location:/download
    restart: unless-stopped
```

and to start

    docker-compose up -d
    
    
### Without Docker

Requires Python 3.7+ 

Clone this repository:

    git clone https://gitlab.com/colethedj/stream_auto_archiver.git && cd saa

(Optional, but recommended) - Create Python virtual environment:

    python3 -m venv saa && source saa/bin/activate

Install Dependencies:
    
    pip3 install -r requirements.txt

and then to run (see configuration section on how to configure)
    
    python3 saa/saa.py --config-file config/config.yml --streamers-file config/streamers.yml
  
View other command line options with `python3 saa/saa.py --help`

## Configuration
 
**Configure streamers.yml**

In this file is where you can configure all the streams to archive. 
The sites that are supported depends on Streamlink. 

There are various optional arguments you can add - see [streamer-args.md](docs/streamer-args.md) for more detailed options.

Basic usage example:
```yaml
streamers:
    TwitchStream:
      url: "https://twitch.tv/channel" # url to send to Streamlink
      name: "TwitchStream" 
      split_time: 3600 # rough length of each chunk in seconds
      download_directory: "/download/TwitchStream" # for the docker container make sure this is /download
      
      streamlink_args: # list of any extra command line arguments to send to Streamlink
        - "--twitch-disable-hosting"
        
      rclone: # to enable rclone to move completed chunks for this stream (optional)
        remote_dir: "DemoRemote:/location/to/move/to"
    
```

**Configure config.yml**

This includes general options

Example:
```yaml
config:
    log_level: "INFO"
    
rclone:
  config: "/config/rclone.conf"
  default_operation: "move"
```



## TODO

View [TODO.md](TODO.md)
