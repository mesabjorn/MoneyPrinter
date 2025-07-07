from pathlib import Path


SONGPATH = Path("resources/songs")


SONGS = [filename for filename in SONGPATH.iterdir() if filename.suffix == ".mp3"]
