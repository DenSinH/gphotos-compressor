"""
Build up a json cache containing video sizes
for all the user's videos.
"""
from photos import *

from pathlib import Path
import os.path
import json
import threading
import concurrent.futures as fut


def build_cache(cache_file: Path | str, extend=True, max_workers=8):
    """ Build up a file size cache, possibly extending an existing cache """
    file_size_cache = {}
    if extend and os.path.exists(cache_file):
        with open(cache_file, "r+") as f:
            file_size_cache = json.load(f)

    service = authenticate()
    lock = threading.Lock()
    with fut.ThreadPoolExecutor(max_workers=max_workers) as pool:

        # wrapper function to get and set media item file size
        # in the cache
        def _get_set_file_size(media_item):
            try:
                file_size = get_file_size(media_item)
                with lock:
                    file_size_cache[media_item['id']] = file_size
                    with open(cache_file, "w+") as f:
                        json.dump(file_size_cache, f, indent=2)
            except Exception:
                print(f"Failed to get and dump file size for {media_item['id']}")
                pass

        futures = set()
        for media_item in get_videos(service):
            if is_compressed(media_item):
                # item is already compressed, no need to get file size
                continue
            if not is_video(media_item):
                # item is not a video, no need to get file size
                continue
            if media_item['id'] in file_size_cache:
                continue

            # retrieve media item file size
            futures.add(pool.submit(_get_set_file_size, media_item))

        fut.wait(futures)


if __name__ == '__main__':
    build_cache("sizes.json")
