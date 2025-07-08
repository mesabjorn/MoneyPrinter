import json
import random
import os

from backend.project.AIVideoProject import AIVideoProject
from backend.MyHTTPException import MyHTTPException
from backend.gpt import generate_metadata
from backend.video import generate_subtitles, combine_videos, generate_video
from backend.tiktokvoice import tts
from backend.youtube import upload_video
   
from flask import Flask, Request, request, jsonify, Response 
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

from backend import LOGGER

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

def select_song():
    return random.choice(resources.resources.SONGS)

@app.route("/api/generate", methods=["POST"])
def generate_endpoint() -> Response:
    result, err = generate(request)
    if result:
        return Response(
            response=json.dumps(result),
            status=200,
            mimetype="application/json"
        )
    elif err:
        return err.to_response()
    else:
        return MyHTTPException(500, "Unknown error").to_response()
    


def generate(request: Request) -> tuple[dict|None,MyHTTPException|None]:

    project = AIVideoProject(request.get_json())
    
    LOGGER.info(f"Generating video for '{project.config.videoSubject}'")

    project.generate_script()
    project.get_search_terms()

    video_paths = project.download_videos()

    # Check if video_paths is empty
    if len(project.videos)==0:
        print(colored("[-] No videos found to download.", "red"))
        return None, MyHTTPException(400, "No videos found to download on pexels api.")


    project.generate_tts()
    project.get_subtitles()

    project.make_final_video()

    return {
        "status": "success",
        "message": "Video generated!",
        "data": str(project.root / "output" / "final.mp4"),
    },None

    # Define metadata for the video, we will display this to the user, and use it for the YouTube upload
    title, description, keywords = generate_metadata(
        project_config.videoSubject, script, project_config.aiModel, project_dir / "keywords.json"
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
