from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
import googleapiclient.errors
from google.auth.transport.requests import Request
import datetime
import dateutil.parser
import pickle
import requests
import os
import ffmpeg
import exiftool
import json
from pathlib import Path
import time

DOWNLOAD_FOLDER = ".download"


def authenticate(credentials_file="credentials.json", token_file="token.pkl") -> Resource:
    """ Authenticate and create the API client """
    SCOPES = [
        'https://www.googleapis.com/auth/photoslibrary',
        'https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata'
    ]
    creds = None

    # check if the token.pkl file exists
    if os.path.exists(credentials_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)

    # if there are no valid credentials, prompt the user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # save the credentials for the next run
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)

    return build('photoslibrary', 'v1', credentials=creds, static_discovery=False)


def is_video(media_item):
    """ Check whether the given media item is a video """
    mime_type = media_item["mimeType"]
    return mime_type.startswith("video")


def is_compressed(media_item):
    """ Check whether the media item was already compressed.
    We simply validate that the file extension is .cmp.something."""
    download_path = get_download_path(media_item, create=False)
    return ".cmp" in download_path.suffixes


def get_atime(media_item):
    """ Get the create time for the media item from the metadata """
    return dateutil.parser.parse(media_item["mediaMetadata"]["creationTime"])


def get_download_url(media_item):
    """ Get the download URL for the media item """
    base_url = media_item["baseUrl"]
    if is_video(media_item):
        return base_url + "=dv"
    return base_url + "=d"


def get_download_path(media_item, create=True) -> Path:
    """ Get the download path for a media item """
    folder = Path(DOWNLOAD_FOLDER) / media_item["id"]
    if create:
        os.makedirs(folder, exist_ok=True)
    return folder / media_item['filename']


def get_file_size(media_item, file_size_cache=None):
    """ Get the file size of a media item.
    We first check a provided memory cache, then we check whether the
    media file has been downloaded already, finally we check the
    size with a HEAD request to the download URL. """

    # check memory cache
    if file_size_cache is not None and media_item["id"] in file_size_cache:
        return file_size_cache[media_item["id"]]

    # check downloaded file
    download_path = get_download_path(media_item, create=False)
    if os.path.exists(download_path):
        return os.path.getsize(download_path)

    # file size with HEAD request
    print(f"Retrieving file size for {media_item['id']}")
    download_url = get_download_url(media_item)
    res = requests.request(
        "HEAD",
        download_url,
        headers={
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
    )
    if not res.ok:
        print(f"Failed to retrieve file size for {media_item['id']}")
        return 0

    print("Checked file size for", download_url)
    return int(res.headers["Content-Length"])


def update_media_created(media_item, filepath):
    """ Update the date created, date modified, and also the
    'Media Created' field, which is where Google Photos gets the
    media date from. """
    print("Update date created for", filepath)
    atime = get_atime(media_item)
    os.utime(filepath, (atime.timestamp(), atime.timestamp()))

    with exiftool.ExifToolHelper() as et:
        et.execute(
            "-P", "-v2",
            f"-FileCreateDate<FileModifyDate",
            f"-AllDates<FileModifyDate",
            "-quicktime:CreateDate<FileModifyDate",
            "-quicktime:ModifyDate<FileModifyDate",
            "-quicktime:TrackCreateDate<FileModifyDate",
            "-quicktime:TrackModifyDate<FileModifyDate",
            "-quicktime:MediaCreateDate<FileModifyDate",
            "-quicktime:MediaModifyDate<FileModifyDate",
            "-overwrite_original",
            str(filepath)
        )


def download_media(media_item):
    """ Download a media item to its canonical download path. """
    filepath = get_download_path(media_item)
    download_url = get_download_url(media_item)

    if not os.path.exists(filepath):
        response = requests.get(download_url)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            update_media_created(media_item, filepath)
            print(f"Downloaded {filepath}")
        else:
            raise Exception(f"Failed to download {filepath}")
    else:
        update_media_created(media_item, filepath)


def compress_media(media_item) -> Path:
    """ Compress a video, and return compressed media path """
    filename = get_download_path(media_item)
    print(f"Compressing {filename}")
    if is_video(media_item):
        output_file = filename.with_suffix(".cmp" + filename.suffix)

        if os.path.exists(output_file):
            return output_file

        # read file data
        video = ffmpeg.input(filename)

        # create ffmpeg output stream
        stream = ffmpeg.output(
            video,
            str(output_file),
            vcodec="libx264",
            crf=28,  # standard
            # copy over metadata
            movflags="use_metadata_tags",
            map_metadata="0"
        ).overwrite_output()
        ffmpeg.run(stream)

        # update file metadata
        return output_file
    else:
        raise NotImplementedError()


def get_videos(service: Resource, page_size=100):
    """ Generator looping through all the user's videos """
    today = datetime.datetime.now()
    next_page_token = None
    total_videos = 0

    while True:
        results = service.mediaItems().search(
            body={
                "pageSize": page_size,
                "pageToken": next_page_token,
                "filters": {
                    "dateFilter": {
                        # photos backed up before june 1st, 2021 do NOT
                        # count towards your storage limit
                        "ranges": [
                            {
                                "startDate": {
                                    "year": 2021,
                                    "month": 6,
                                    "day": 1
                                },
                                "endDate": {
                                    "year": today.year,
                                    "month": today.month,
                                    "day": today.day
                                }
                            }
                        ]
                    },
                    "mediaTypeFilter": {
                        # find only videos
                        "mediaTypes": [
                            "VIDEO"
                        ]
                    }
                }
            }
        ).execute()
        items = results.get('mediaItems', [])

        total_videos += len(items)
        print(f"Retrieved {total_videos} items")

        yield from items

        # next page
        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            break


def upload_video(service: Resource, media_item, filepath):
    """ Upload a (compressed) media file """
    # Get the file name
    file_name = os.path.basename(filepath)
    upload_url = 'https://photoslibrary.googleapis.com/v1/uploads'

    # we get the token from the service http credentials, which
    # we loaded in Authorize
    headers = {
        'Authorization': f'Bearer {service._http.credentials.token}',
        'Content-Type': 'application/octet-stream',
        'X-Goog-Upload-File-Name': file_name,
        'X-Goog-Upload-Protocol': 'raw',
    }

    with open(filepath, 'rb') as f:
        data = f.read()

    response = requests.post(upload_url, headers=headers, data=data)

    if response.status_code == 200:
        upload_token = response.text
        return upload_token
    else:
        print(f"Failed to upload video: {response.text}")
        return None


def create_media_item(service: Resource, upload_token, media_item):
    """ Create a media item from an upload token """

    request_body = {
        "newMediaItems": [
            {
                # copy over old description
                "description": media_item.get('description', ''),
                "simpleMediaItem": {
                    "uploadToken": upload_token
                }
            }
        ]
    }

    response = service.mediaItems().batchCreate(body=request_body).execute()

    if 'newMediaItemResults' in response and len(response['newMediaItemResults']) > 0:
        new_media_item = response['newMediaItemResults'][0]['mediaItem']
        return new_media_item
    else:
        print(f"Failed to create media item: {json.dumps(response, indent=2)}")
        return None


def media_exists(service: Resource, media_item):
    try:
        service.mediaItems().get(mediaItemId=media_item["id"]).execute()
        return True
    except googleapiclient.errors.HttpError:
        # media ID not found, it must have been deleted
        return False


def request_media_delete(service: Resource, new_media_item, media_item):
    """ Request media deletion, and wait for the user to delete the media.
    Returns True if the media was deleted, and False if the replacement was deleted. """
    print(f"Please delete {media_item['productUrl']}\n"
          f"    (updated to {new_media_item['productUrl']})\n"
          f"    Or delete the uploaded media to skip this media compression.")

    for i in range(1, 600851475143):
        if not media_exists(service, media_item):
            return True

        if not media_exists(service, new_media_item):
            return False

        # increment wait time every attempt
        time.sleep(min((i // 3) + 1, 5))
    else:
        raise Exception("Failed to validate file deletion...")


def replace_media(service: Resource, media_item, filepath):
    """ Upload a file to replace the current existing media_item """

    # upload the new video
    print("Uploading new media")
    upload_token = upload_video(service, media_item, filepath)
    if not upload_token:
        print("No upload token for media")
        return

    # create a new media item with the uploaded video
    print("Creating new media item")
    new_media_item = create_media_item(service, upload_token, media_item)
    if not new_media_item:
        return

    # delete the old media item
    print(f"Requesting deletion of {media_item['id']}.")
    deleted = request_media_delete(service, new_media_item, media_item)
    return deleted

