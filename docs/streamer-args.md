
This file outlines all the possible options for streamers.yml config.

Required arguments are marked with a `# required` comment.

```yaml
# streamers.yml

streamers:
  SpaceX:
    url: "https://www.youtube.com/user/spacexchannel/live" # required
    name: "SpaceX_YT"
    download_directory: "/download/SpaceX_YT" # recommended... otherwise default is current dir (.)
    split_time: 18000 # default is 3600 (1hr), 
    quality: "best" # Streamlink quality, default is best
    
    streamlink_args: # any extra command line arguments you want to sent to Streamlink
     - "--twitch-disable-hosting"
    
    rclone:
        remote_dir: "DemoRemote:/location/to/move/to" # required
        operation: "move" # default is move, overwrites config.yml
        rclone_config: /config/rclone.conf # default is ~/.config/rclone.conf, overwrites config.yml
        transfers: 4 # rclone --transfers option, default is 4, overwrites config.yml
        
        rclone_args: # if there are any extra rclone command line arguments you want
          - "--create-empty-src-dirs"


```