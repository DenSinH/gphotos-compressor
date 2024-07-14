# GPhotos Compressor

I noticed that some videos I took with my phone were hundreds of megabytes, even when they were not even that long
(just a couple of minutes). Since there is no easy way to compress them using Google Photos, I decided to try and
do it with the API.

Running this script removed about 5GB worth of large videos, from 55GB of media for me.

## What does it do?

This script goes through all of your saved videos newer than June 1st, 2021, above a certain size threshold, compresses
them with FFMpeg (using `H.264` encoding) and re-uploads them. 
*You will be prompted to manually delete the old photos, as there is no way to do this with the API.*

**Disclaimer: the newly uploaded videos will NOT be added to any albums the originals were in, and you might lose
(location) metadata. USE AT YOUR OWN RISK!**

Basically, once you have set up everything, you should first run `get_video_sizes.py`. This will fetch all videos,
and get their file sizes, and cache these results to `sizes.json`. This requires no interaction past allowing
access to manage your Google photos library. 

After that, you should run `replace_large_videos.py`. This will go through all "large" videos (anything >40MB),
will download them to the `.download` folder, compress them with ffmpeg, reupload them to Google photos and prompt you
with the following:
```
Please delete {old_media_url}
    (updated to {new_media_url})
    Or delete the uploaded media to skip this media compression.
```
You can click both URLs to see the old and new video, and possibly compare their sizes.
- If you delete the old photo: the script will continue.
- If you delete the new photo: the script will store -1 as the file size for the media, so it will not be considered
  in subsequent runs, and will continue.

Media that was already compressed (stored with `.cmp.original-extension`, where `original-extension` is `mp4` for `video.mp4` for example)
are also *not* considered in subsequent runs of the script.

## Setting up

- Install the required packages from `requirements.txt` and install `exiftool` (on windows, for example with
chocolatey with `choco install exiftool`).
- Generate credentials for the Google photos API, with the appropriate permissions:
  - Go to [the Google cloud console](https://console.cloud.google.com/)
  - Create a new project, for example `gphotos-compressor`, and open the project, this will
    select it as the active project.
  - Go to [APIS & Services](https://console.cloud.google.com/apis/dashboard) and click "Enable APIs and Services".
  - Search for the "Photos Library API".
  - Enable the [Photos Library API](https://console.cloud.google.com/apis/library/photoslibrary.googleapis.com)
  - You will be lead back to the [APIs & Services tab](https://console.cloud.google.com/apis/api/photoslibrary.googleapis.com/metrics)
  - You will need to configure the [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
    before being able to generate credentials:
    - You might only have the option to select "External", if so, do this and hit next.
    - Give the app a name, for example `gphotos-compressor`.
    - Enter your email as user support email.
    - Add an email (for example your email) as developer contact email.
    - In the scopes section, click "Add or remove scopes". In the window that pops up, search for `photoslibrary`
      and select all available scopes. Most notably, these should include `.../auth/photoslibrary` and `.../auth/photoslibrary.edit.appcreateddata`. 
      Click "update" at the bottom of the side panel when you have done so.
    - Click "save and continue".
    - Add your own email as test user, since we will not be publishing this app. Again click "save and continue".
    - In the final overview screen, click "back to dashboard". We are now ready to generate credentials.
  - Go to the [Credentials tab in APIs & Services](https://console.cloud.google.com/apis/credentials).
  - Click "+ Create credentials" and select "OAuth client ID".
  - Select an application type (I chose Desktop app, I am not sure if this matters at all), and give it a name
    for example `gphotos-compressor`.
  - You will be led back to the Credentials tab, with a modal overlay. Click "download json".
  - Place the downloaded file next to the script, and name it `credentials.json`. These are the credentials
    the script needs to run.
- When running the script for the first time, you will be prompted to click a link. This link will provide
  an access token to the script to manage your Google photos library. Select both checkboxes to allow permission.
  You will then be prompted to close the tab, and the script will start running. The token will be re-used on
  subsequent runs.
