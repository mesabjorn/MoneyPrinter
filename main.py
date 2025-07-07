import hashlib
from pathlib import Path
import random
import os
from uuid import uuid4

from backend.ProjectConfig import ProjectConfig
import resources.resources

from backend.gpt import generate_script, get_search_terms, generate_metadata
from backend.video import save_video, generate_subtitles, combine_videos, generate_video
from backend.search import search_for_stock_videos
from backend.tiktokvoice import tts
from backend.youtube import upload_video

from flask import Flask, request, jsonify
from flask_cors import CORS

from termcolor import colored

from moviepy.config import change_settings
from moviepy.editor import (
    AudioFileClip,
    concatenate_audioclips,
    VideoFileClip,
    CompositeAudioClip,
)

from decouple import config

# Set environment variables
SESSION_ID = config("TIKTOK_SESSION_ID")
openai_api_key = config("OPENAI_API_KEY")
change_settings({"IMAGEMAGICK_BINARY": config("IMAGEMAGICK_BINARY")})
PEXELS_API_KEY = config("PEXELS_API_KEY")


# Initialize Flask
app = Flask(__name__)
CORS(app)

# Constants
HOST = "0.0.0.0"
PORT = 8080
AMOUNT_OF_STOCK_VIDEOS = 5
GENERATING = False


def select_song():
    return random.choice(resources.resources.SONGS)


def parse_json(json_data: dict) -> ProjectConfig:
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


def init_project(title: str) -> Path:
    project_id = hashlib.sha256(title.encode()).hexdigest()
    project_dir = Path(f"./creations/{project_id}")
    subtitles_dir = project_dir / "subtitles"
    video_dir = project_dir / "video"
    output_dir = project_dir / "output"

    project_dir.mkdir(parents=True, exist_ok=True)
    subtitles_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    return project_dir


# Generation Endpoint
@app.route("/api/generate", methods=["POST"])
def generate():
    project_config = parse_json(request.get_json())

    # Print little information about the video which is to be generated
    print(colored("[Video to be generated]", "blue"))
    print(colored(f"   Subject: {project_config.videoSubject}", "blue"))
    print(
        colored(f"   AI Model: {project_config.aiModel}", "blue")
    )  # Print the AI model being used
    print(
        colored(f"   Custom Prompt: {project_config.customPrompt}", "blue")
    )  # Print the AI model being used

    project_dir = init_project(project_config.videoSubject)

    voice_prefix = project_config.voice[:2]

    # Generate a script
    script = generate_script(
        project_config
    )  # Pass the AI model to the script generation

    # Let user know
    print(colored("[+] Script generated!\n", "green"))

    nvideos = len(list(project_dir.glob("video/*.mp4")))
    if nvideos == 0:
        # dont redownload if there are already videos in the project directory
        # Generate search terms
        search_terms = get_search_terms(
            project_config.videoSubject,
            AMOUNT_OF_STOCK_VIDEOS,
            script,
            project_config.aiModel,
        )

        # Search for a video of the given search term
        video_urls = []

        # Defines how many results it should query and search through
        it = 15

        # Defines the minimum duration of each clip
        min_dur = 10

        # Loop through all search terms,
        # and search for a video of the given search term
        for search_term in search_terms:
            found_urls = search_for_stock_videos(
                search_term, PEXELS_API_KEY, it, min_dur
            )
            # Check for duplicates
            for url in found_urls:
                if url not in video_urls:
                    video_urls.append(url)
                    break

        # Check if video_urls is empty
        if not video_urls:
            print(colored("[-] No videos found to download.", "red"))
            return jsonify(
                {
                    "status": "error",
                    "message": "No videos found to download.",
                    "data": [],
                }
            )

        # Define video_paths
        video_paths = []

        # Let user know
        print(colored(f"[+] Downloading {len(video_urls)} videos...", "blue"))

        # Save the videos
        for video_url in video_urls:
            try:
                saved_video_path = save_video(
                    video_url, project_dir / "video" / f"{uuid4()}.mp4"
                )
            except Exception as e:
                print(colored(f"[-] Could not download video: {video_url}", "red"))

        # Let user know
        print(colored("[+] Videos downloaded!", "green"))

    # Split script into sentences
    sentences = script.split(". ")

    # Remove empty strings
    sentences = list(filter(lambda x: x != "", sentences))
    audio_paths = []

    tts_path = project_dir / "video" / "tts.mp3"
    audio_paths = [
        AudioFileClip(str(p))
        for p in (project_dir / "video" / "audio_parts").glob("*.mp3")
    ]
    video_paths = [p for p in (project_dir / "video").glob("*.mp4")]

    if len(audio_paths) == 0:
        # Generate TTS for every sentence
        for i, sentence in enumerate(sentences):
            current_tts_path = project_dir / "video" / "audio_parts"
            audio_part = tts(
                sentence, project_config.voice, audio_parts=current_tts_path, i=i
            )
            audio_clip = AudioFileClip(str(audio_part))
            audio_paths.append(audio_clip)

    # Combine all TTS files using moviepy
    if not tts_path.exists():
        final_audio = concatenate_audioclips(audio_paths)
        final_audio.write_audiofile(tts_path)

    subtitles_path = project_dir / "video" / "subtitles.srt"
    try:
        if not subtitles_path.exists():
            generate_subtitles(
                audio_path=tts_path,
                sentences=sentences,
                audio_clips=audio_paths,
                voice=voice_prefix,
                target=subtitles_path,
            )
    except Exception as e:
        print(colored(f"[-] Error generating subtitles: {e}", "red"))
        subtitles_path = None

    combined_video_path = project_dir / "output" / "combined.mp4"
    if not combined_video_path.exists():
        # Concatenate videos
        temp_audio = AudioFileClip(str(tts_path))
        combined_video_path = combine_videos(
            video_paths,
            temp_audio.duration,
            5,
            project_config.threads,
            project_dir / "output" / "combined.mp4",
        )

    # Put everything together
    try:
        final_video_path = generate_video(
            str(combined_video_path),
            str(tts_path),
            str(subtitles_path),
            project_config.threads,
            project_config.subtitlesPosition,
            project_config.color,
            target=project_dir / "output" / "final.mp4",
        )
    except Exception as e:
        print(colored(f"[-] Error generating final video: {e}", "red"))
        return jsonify(
            {
                "status": "error",
                "message": "Error generating final video.",
                "data": [],
            }
        )

    # Define metadata for the video, we will display this to the user, and use it for the YouTube upload
    title, description, keywords = generate_metadata(
        project_config.videoSubject, script, project_config.aiModel
    )

    print(colored("[-] Metadata for YouTube upload:", "blue"))
    print(colored("   Title: ", "blue"))
    print(colored(f"   {title}", "blue"))
    print(colored("   Description: ", "blue"))
    print(colored(f"   {description}", "blue"))
    print(colored("   Keywords: ", "blue"))
    print(colored(f"  {', '.join(keywords)}", "blue"))

    if project_config.automateYoutubeUpload:
        # Start Youtube Uploader
        # Check if the CLIENT_SECRETS_FILE exists
        client_secrets_file = os.path.abspath("./client_secret.json")
        SKIP_YT_UPLOAD = False
        if not os.path.exists(client_secrets_file):
            SKIP_YT_UPLOAD = True
            print(
                colored(
                    "[-] Client secrets file missing. YouTube upload will be skipped.",
                    "yellow",
                )
            )
            print(
                colored(
                    "[-] Please download the client_secret.json from Google Cloud Platform and store this inside the /Backend directory.",
                    "red",
                )
            )

        # Only proceed with YouTube upload if the toggle is True  and client_secret.json exists.
        if not SKIP_YT_UPLOAD:
            # Choose the appropriate category ID for your videos
            video_category_id = "28"  # Science & Technology
            privacyStatus = "private"  # "public", "private", "unlisted"
            video_metadata = {
                "video_path": os.path.abspath(str(final_video_path)),
                "title": title,
                "description": description,
                "category": video_category_id,
                "keywords": ",".join(keywords),
                "privacyStatus": privacyStatus,
            }

            # Upload the video to YouTube
            try:
                # Unpack the video_metadata dictionary into individual arguments
                video_response = upload_video(
                    video_path=video_metadata["video_path"],
                    title=video_metadata["title"],
                    description=video_metadata["description"],
                    category=video_metadata["category"],
                    keywords=video_metadata["keywords"],
                    privacy_status=video_metadata["privacyStatus"],
                )
                print(f"Uploaded video ID: {video_response.get('id')}")
            except Exception as e:
                print(f"An HTTP error occurred:{e}")

    video_clip = VideoFileClip(str(final_video_path))
    if project_config.useMusic:
        # Select a random song
        song_path = select_song()

        # Add song to video at 30% volume using moviepy
        original_duration = video_clip.duration
        original_audio = video_clip.audio
        song_clip = AudioFileClip(song_path).set_fps(44100)

        # Set the volume of the song to 10% of the original volume
        song_clip = song_clip.volumex(0.1).set_fps(44100)

        # Add the song to the video
        comp_audio = CompositeAudioClip([original_audio, song_clip])
        video_clip = video_clip.set_audio(comp_audio)
        video_clip = video_clip.set_fps(30)
        video_clip = video_clip.set_duration(original_duration)
        video_clip.write_videofile(
            project_dir / "output" / "final_audio.mp4",
            threads=project_config.threads or 1,
        )

    # Let user know
    print(colored(f"[+] Video generated: {final_video_path}!", "green"))

    # Stop FFMPEG processes
    if os.name == "nt":
        # Windows
        os.system("taskkill /f /im ffmpeg.exe")
    else:
        # Other OS
        os.system("pkill -f ffmpeg")

    # Return JSON
    return jsonify(
        {
            "status": "success",
            "message": f"Video generated! See {final_video_path} for result.",
            "data": str(final_video_path),
        }
    )


@app.route("/api/cancel", methods=["POST"])
def cancel():
    print(colored("[!] Received cancellation request...", "yellow"))

    global GENERATING
    GENERATING = False

    return jsonify({"status": "success", "message": "Cancelled video generation."})


if __name__ == "__main__":
    # Run Flask App
    app.run(debug=True, host=HOST, port=PORT)
