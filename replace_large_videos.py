from photos import *

from pathlib import Path
import json
import os.path


def replace_large_videos(file_size_cache_path: Path | str, size_threshold=40 * 1024 * 1024):
    """ Replace all large videos for the user.
    This requires running get_video_sizes.py first, in order to build up the video
    size file cache. Compresses all videos larger than size_threshold, which is 20MB by
    default. """

    # find size cache file
    if not os.path.exists(file_size_cache_path):
        raise Exception("File size cache not found, did you run get_video_sizes.py?")

    # load size cache file
    with open(file_size_cache_path, "r") as f:
        file_size_cache = json.load(f)

    service = authenticate()

    # we do not want to do this in parallel, since compressing a video
    # uses up all available CPU resources, and we also want to make sure
    # the user's account is not flooded with compressed videos,
    # so we upload / prompt the user with the updated videos one-by-one
    for i, item in enumerate(get_videos(service)):
        if is_compressed(item):
            # already compressed item
            continue
        if not is_video(item):
            # only compress videos
            continue

        file_size = get_file_size(item, file_size_cache)
        print(f"Video {i} ({get_atime(item)}), file size {file_size // (1024 * 1024)}MB")

        # Check if the item is a video or a large photo
        if file_size >= size_threshold:
            download_media(item)
            compressed = compress_media(item)

            if not replace_media(service, item, compressed):
                # media was NOT replaced, update size in cache in order
                # to prevent trying to replace it again
                print("Did NOT replace media, setting file size to -1")
                file_size_cache[item['id']] = -1
                with open(file_size_cache_path, "w+") as f:
                    json.dump(file_size_cache, f)


if __name__ == '__main__':
    replace_large_videos("sizes.json")
