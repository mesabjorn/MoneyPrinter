from dataclasses import dataclass



@dataclass
class ProjectConfig:
    videoSubject: str
    voice: str = "en_us_001"
    paragraphNumber: int = 1
    aiModel: str = "gpt-3.5-turbo-1106"
    threads: int = 2
    subtitlesPosition: str = "center,bottom"
    color: str = "Yellow"
    useMusic: bool = False
    automateYoutubeUpload: bool = False
    customPrompt: str = ""

   