This file outlines all the possible options for streamers.yml config.

Required arguments are marked with a `# required` comment.

```yaml
# streamers.yml

streamers:
  MyYouTubeStreamer:
    enabled: True                                              # use this to cleanly disable archiving of streams (lets rclone cleanup all files from that stream)
    url: "https://www.youtube.com/user/MyYouTubeStreamer/live" # required
    name: "MyYouTubeStreamer"
    download_directory: "/download/MyYouTubeStreamer"          # Leave this to /download for the docker image. Default is "." (current directory)
    split_time: 18000                                          # Stream split time in seconds. Default is 3600 (1hr). To disable spliting, set this to a high value.
    quality: "best"                                            # Streamlink quality setting, default is best.
    
    streamlink_args:                                           # any extra command line arguments you want to sent to Streamlink.
     - "--twitch-disable-hosting"
     - "--youtube-bypass-429"
    
    # if you do not want rclone to run for this stream, remove this section
    rclone:
        remote_dir: "DemoRemote:/location/to/move/to"          # required
        operation: "move"                                      # default is move, overrides config.yml.
        rclone_config: /config/rclone.conf                     # default is ~/.config/rclone.conf, overrides config.yml.
        transfers: 4                                           # rclone --transfers option, default is 4, overrides config.yml.
        
        rclone_args:                                           # any other rclone command line arguments.
          - "--bwlimit"
          - "2M"


```
