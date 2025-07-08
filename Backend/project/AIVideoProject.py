
import hashlib
import json
from pathlib import Path
from typing import List
from uuid import uuid4

from backend import LOGGER, gpt
from backend.project.ProjectConfig import ProjectConfig
from backend.search import get_stock_video

from moviepy.editor import (
    AudioFileClip,
    concatenate_audioclips,
    VideoFileClip,
    CompositeAudioClip,
)

from backend.tiktokvoice import tts
from backend.video import combine_videos, generate_subtitles, generate_video

AMOUNT_OF_STOCK_VIDEOS = 5

def parse_json(json_data: dict) -> ProjectConfig:
    """
    Parse a JSON object into a ProjectConfig object.
    """
    return ProjectConfig(
        videoSubject=json_data.get("videoSubject", ""),
        customPrompt=json_data.get("customPrompt", ""),
        voice=json_data.get("voice", "en_us_001"),
        paragraphNumber=int(json_data.get("paragraphNumber", 1) or 1),
        aiModel=json_data.get("aiModel", "gpt-3.5-turbo-1106"),
        threads=int(json_data.get("threads", 2) or 2),
        subtitlesPosition=json_data.get("subtitlesPosition", "center,bottom"),
        color=json_data.get("color", "Yellow"),
        useMusic=bool(json_data.get("useMusic", False)),
        automateYoutubeUpload=bool(json_data.get("automateYoutubeUpload", False)),
    )


class AIVideoProject:
    """
    A class representing an AI video project.
    """
    config: ProjectConfig
    project_id: str
    metadata: dict
    _project_dir: Path
    _initialized: bool = False
    script: str
    search_terms: list[str]
    _subdirs = {
        "video": "video",
        "output": "output",
        "audio_parts": "audio_parts",
    }
    
    def __init__(self,request_data:dict):
        self.config = parse_json(request_data)
        self.project_id = hashlib.sha256(self.config.videoSubject.encode()).hexdigest()
        self.init()
    
    def init(self) -> bool:
        """
        Initialize the project directory and metadata.
        """
        self._project_dir = Path(f"./creations/{self.project_id}")    

        self._project_dir.mkdir(parents=True, exist_ok=True)
        
        for subdir in self._subdirs.values():
            (self._project_dir/subdir).mkdir(parents=True, exist_ok=True)
        
        self.metadata = {
            "title": self.config.videoSubject,
            "customPrompt": self.config.customPrompt,            
            "voice": self.config.voice,
            "aiModel": self.config.aiModel,                
            "subtitlesPosition": self.config.subtitlesPosition,
            "color": self.config.color,
            "useMusic": self.config.useMusic,
            "automateYoutubeUpload": self.config.automateYoutubeUpload,
        }

        self.save_metadata()
        self._initialized = True
        return self._initialized

    def save_metadata(self):
        with open(self._project_dir/"metadata.json", "w") as f:
            json.dump(self.metadata, indent=4, fp=f)

    def get_project_dir(self) -> Path:
        return self._project_dir

    def get_subdir(self,subdir:str) -> Path|None:
        if not self._initialized:
            raise Exception("Project not initialized")
        if subdir in self._subdirs:
            return self._project_dir / subdir
        return None
        
    @property
    def root(self)->Path:
        return self._project_dir


    @property
    def videos(self)->list[Path]:
        return list((self.root/"video").glob("*.mp4"))

    @property
    def audio_parts(self)->List[AudioFileClip]:
        return [AudioFileClip(str(p)) for p in (self.root / "audio_parts").glob("*.mp3")]


    def generate_script(self):
        """
        Generate a script for the project using the AI model.
        """
        script_path = self._project_dir/".script"

        src = self.config.aiModel if not script_path.exists() else f"file: '{script_path}'"

        if not script_path.exists():
            script = gpt.generate_script(
                custom_prompt=self.config.customPrompt,
                video_subject=self.config.videoSubject,
                paragraph_number=self.config.paragraphNumber,
                voice=self.config.voice,
                model=self.config.aiModel)
            with open(script_path, "w") as f:
                f.write(script)

        with open(script_path, "r") as f:
            self.script = f.read()
        
        LOGGER.info(f"Script obtained from '{src}'.")

        return self.script

    def get_search_terms(self)->list[str]:
        """
        Generate search terms for the project.
        """
        search_terms_path = self._project_dir / "search_terms.json"
        if not search_terms_path.exists():
            search_terms = gpt.get_search_terms(
            self.config.videoSubject,
            AMOUNT_OF_STOCK_VIDEOS,
            self.script,
            self.config.aiModel,
            self._project_dir / "search_terms.json"
            )
            with open(search_terms_path, "w") as f:
                json.dump(search_terms, indent=4, fp=f)
            LOGGER.info(f"Search terms generated with llm for '{self.config.videoSubject}'.")
        with open(search_terms_path, "r") as f:
            self.search_terms = json.load(f)
        LOGGER.info(f"Search terms obtained from '{search_terms_path}'.")
        return self.search_terms
        
    def download_videos(self) -> List[Path]:
        """
        Search for a video of the given search term and download them to the target path.

        Args:
            search_terms (List[str]): The search terms to search for.
            target_path (Path): The path to save the videos to.

        Returns:    
            List[Path]: A list of paths to the saved videos. 
        """
        if  len(self.videos) > 0:
            return self.videos
        
        video_results = []

        # Defines how many results it should query and search through
        it = 15

        # Defines the minimum duration of each clip
        min_dur = 10
        saved_urls = []
        # Loop through all search terms, and search for a video of the given search term.
        for search_term in self.search_terms:
            video = get_stock_video(search_term, it, min_dur, saved_urls)
            if video:
                vidfile = video.save(self.root/"video"/f"{uuid4()}.mp4")
                video_results.append(vidfile)
                saved_urls.append(video.id)
        LOGGER.info(f"Videos downloaded from pexels api for '{self.config.videoSubject}'.")
        return video_results

    def generate_tts(self):
        if not self.script:
            raise Exception("Cannot generate TTS, script not generated")
        sentences = self.get_sentences()
        audio_paths = []

        tts_path = self.root / "tts.mp3"
                
        if len(self.audio_parts) == 0:
            # Generate TTS for every sentence
            for i, sentence in enumerate(sentences):
                current_tts_path = self.root / "audio_parts"
                audio_part = tts(
                    sentence, self.config.voice, audio_parts=current_tts_path, i=i
                )
                audio_clip = AudioFileClip(str(audio_part))
                audio_paths.append(audio_clip)

        # Combine all TTS files using moviepy
        if not tts_path.exists():
            final_audio = concatenate_audioclips(audio_paths)
            final_audio.write_audiofile(tts_path)
        self.tts_path = tts_path
        


    def get_sentences(self):
        sentences = self.script.split(". ")
        sentences = list(filter(lambda x: x != "", sentences))
        return sentences

    def get_subtitles(self):
        subtitles_path = self.root / "subtitles.srt"
        
        if not subtitles_path.exists():
                generate_subtitles(
                    audio_path=self.tts_path,
                    sentences=self.get_sentences(),
                    audio_clips=self.audio_parts,
                    voice= self.config.voice[:2],
                    target=subtitles_path,
                )
        with open(subtitles_path, "r") as f:
            self.subtitles = f.read()
        LOGGER.info(f"Subtitles obtained from '{subtitles_path}'.")
        return self.subtitles

    def make_final_video(self):
        combined_video_path = self.root / "output" / "combined.mp4"
        if not combined_video_path.exists():
            # Concatenate videos
            temp_audio = AudioFileClip(str(self.tts_path))
            combined_video_path = combine_videos(
                self.videos,
                temp_audio.duration,
                5,
                self.config.threads,
                combined_video_path
            )
        LOGGER.info(f"Videos combined into '{combined_video_path}'.")

        # Put everything together        
        final_video_path = generate_video(
                str(combined_video_path),
                str(self.tts_path),
                str(self.root / "subtitles.srt"),
                self.config.threads,
                self.config.subtitlesPosition,
                self.config.color,
            target=self.root / "output" / "final.mp4",
        )
        LOGGER.info(f"Final video generated into '{final_video_path}'.")

        return final_video_path
