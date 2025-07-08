from pathlib import Path
import requests
from dataclasses import dataclass
from typing import List
from termcolor import colored
from decouple import config

PEXELS_API_KEY = config("PEXELS_API_KEY")

@dataclass
class VideoResult:
    id: str
    url: str
    duration: int
    width: int
    height: int

    def __str__(self):
        return f"VideoResult(url={self.url}, duration={self.duration}, width={self.width}, height={self.height})"
    
    def __repr__(self):
        return self.__str__()
    
    
    def save(self, target_path: Path) -> Path|None:
        """
            Saves a video to the local directory.
        """
        r = requests.get(self.url, timeout=10)
        if r.status_code != 200:
            print(colored(f"Saving video failed for url: '{self.url}' to '{target_path}'", "red"))
            return None
        
        with target_path.open("wb") as f:
            f.write(r.content)
        return target_path
  

def get_stock_video(query: str, n: int, min_dur: int, saved_urls: List[str]) -> VideoResult|None:
    """
    Searches for stock videos based on a query.

    Args:
        query (str): The query to search for.
        n (int): The number of videos to search for.
        min_dur (int): The minimum duration of the videos to search for.

    Returns:
        VideoResult: A stock video or None if no video is found.
    """
    
    # Build headers
    headers = {
        "Authorization": PEXELS_API_KEY
    }

    # Build URL
    qurl = f"https://api.pexels.com/videos/search?query={query}&per_page={n}"

    # Send the request
    r = requests.get(qurl, headers=headers,timeout=10)

    # Parse the response
    response = r.json()

    # Parse each video    
    result: VideoResult = None
    video_res = 0
    videos = response["videos"]
    if len(videos) == 0:
        print(colored(f"[-] No videos found for query: '{query}'", "red"))
        return None
    
    # loop through each video in the result
    for video in filter(lambda x: x["duration"] >= min_dur, videos): # filter out videos that are less than the minimum duration
        video_files = video["video_files"]            
        
        best_url = ""

        # loop through each url to determine the best quality
        for video_file in video_files:
            url = video_file["link"]
            if url in saved_urls:
                continue
            width = video_file["width"]
            height = video_file["height"]
            resolution = width*height
            if ".com/video-files" in url:
                # Only save the URL with the largest resolution
                if resolution > video_res:
                    best_url = url
                    video_res = width*height
        if len(best_url) > 0:
            print(colored(f"\t=> \"{query}\" found {len(video_files)} videos.", "cyan"))
            return VideoResult(id=video["id"], url=best_url, duration=video["duration"], width=width, height=height)
    print(colored(f"[-] No videos found for query: '{query}'", "red"))
    return None
    
                

