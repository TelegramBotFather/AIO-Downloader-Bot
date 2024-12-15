import glob
import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union, Dict
import aiohttp
import re
from urllib.parse import urlparse, urljoin, unquote
import json
from telegram import InputMediaAnimation
import yt_dlp
import asyncio
import math
import cv2
import time
import pymongo
import requests
from PIL import Image
import pyrogram
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.types import Message, InlineKeyboardMarkup as PyrogramInlineKeyboardMarkup
from pyrogram.types import InlineKeyboardButton as PyrogramInlineKeyboardButton
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from pyrogram.errors import FloodWait, MediaEmpty
from pyrogram.types import Message, ChatPermissions, CallbackQuery
from pyrogram.errors import UserNotParticipant
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv("Smokie.env")

# Configuration
class Config:
    # Pyrogram app details
    API_ID = os.getenv("TELEGRAM_API_ID")  # Load from environment variables
    API_HASH = os.getenv("TELEGRAM_API_HASH")
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    ADMIN_USER_IDS = [int(user_id) for user_id in os.getenv("ADMIN_USER_IDS", "").split(",") if user_id]
    RAPID_API_KEY = os.getenv("RAPID_API_KEY")
    RAPID_API_URL = "https://instagram-scraper-api-stories-reels-va-post.p.rapidapi.com/"
    RAPID_API_HEADERS = {
        "x-rapidapi-key": RAPID_API_KEY,
        "x-rapidapi-host": "instagram-scraper-api-stories-reels-va-post.p.rapidapi.com"
    }

    TEMP_DIR = Path("temp")
    YT_COOKIES_PATH = "cookies.txt"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Referer': 'https://www.pinterest.com/',
    }
    MAX_IMAGE_SIZE = {
        'width': 3000,
        'height': 3000
    }

async def sanitize_filename(title: str) -> str:
    """
    Sanitize file name by removing invalid characters.
    """
    title = re.sub(r'[<>:"/\\|?*]', '', title)
    title = title.replace(' ', '_')
    return f"{title[:50]}_{int(time.time())}"

async def validate_youtube_url(url: str) -> bool:
    """
    Validate if the provided URL is a valid YouTube link.
    """
    return url.startswith(('https://www.youtube.com/', 'https://youtube.com/', 'https://youtu.be/'))

async def format_size(size_bytes: int) -> str:
    """
    Format file size into human-readable string.
    """
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

async def format_duration(seconds: int) -> str:
    """
    Format video duration into human-readable string.
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

async def prepare_thumbnail(thumbnail_url: str, output_path: str) -> str:
    """
    Download and prepare the thumbnail image to meet Telegram's requirements.
    """
    try:
        response = requests.get(thumbnail_url)
        if response.status_code == 200:
            thumbnail_temp_path = f"{output_path}_thumbnail.jpg"
            with open(thumbnail_temp_path, 'wb') as f:
                f.write(response.content)

            # Resize the thumbnail while maintaining aspect ratio
            thumbnail_resized_path = f"{output_path}_thumb.jpg"
            with Image.open(thumbnail_temp_path) as img:
                # Convert to RGB to ensure compatibility
                img = img.convert('RGB')
                
                # Calculate the resize strategy to maintain aspect ratio
                img.thumbnail((320, 320), Image.Resampling.LANCZOS)
                
                # Create a white background
                background = Image.new('RGB', (320, 320), (255, 255, 255))
                
                # Calculate position to center the thumbnail
                offset = ((320 - img.width) // 2, (320 - img.height) // 2)
                
                # Paste the thumbnail onto the white background
                background.paste(img, offset)
                
                # Save with high quality
                background.save(thumbnail_resized_path, "JPEG", quality=85)

            # Remove the temporary file
            os.remove(thumbnail_temp_path)
            return thumbnail_resized_path
    except Exception as e:
        print(f"Error preparing thumbnail: {e}")
    return None

async def sanitize_filename(title: str) -> str:
    """
    Sanitize file name by removing invalid characters.
    """
    title = re.sub(r'[<>:"/\\|?*]', '', title)
    title = title.replace(' ', '_')
    return f"{title[:50]}_{int(time.time())}"

async def validate_youtube_url(url: str) -> bool:
    """
    Validate if the provided URL is a valid YouTube link.
    """
    return url.startswith(('https://www.youtube.com/', 'https://youtube.com/', 'https://youtu.be/'))

async def format_size(size_bytes: int) -> str:
    """
    Format file size into human-readable string.
    """
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

async def format_duration(seconds: int) -> str:
    """
    Format video duration into human-readable string.
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

async def prepare_thumbnail(thumbnail_url: str, output_path: str) -> str:
    """
    Download and prepare the thumbnail image to meet Telegram's requirements.
    """
    try:
        response = requests.get(thumbnail_url)
        if response.status_code == 200:
            thumbnail_temp_path = f"{output_path}_thumbnail.jpg"
            with open(thumbnail_temp_path, 'wb') as f:
                f.write(response.content)

            # Resize the thumbnail while maintaining aspect ratio
            thumbnail_resized_path = f"{output_path}_thumb.jpg"
            with Image.open(thumbnail_temp_path) as img:
                # Convert to RGB to ensure compatibility
                img = img.convert('RGB')
                
                # Calculate the resize strategy to maintain aspect ratio
                img.thumbnail((320, 320), Image.Resampling.LANCZOS)
                
                # Create a white background
                background = Image.new('RGB', (320, 320), (255, 255, 255))
                
                # Calculate position to center the thumbnail
                offset = ((320 - img.width) // 2, (320 - img.height) // 2)
                
                # Paste the thumbnail onto the white background
                background.paste(img, offset)
                
                # Save with high quality
                background.save(thumbnail_resized_path, "JPEG", quality=85)

            # Remove the temporary file
            os.remove(thumbnail_temp_path)
            return thumbnail_resized_path
    except Exception as e:
        print(f"Error preparing thumbnail: {e}")
    return None

class MongoDBConnection:
    def __init__(self, connection_string):
        """
        Initialize MongoDB connection
        
        Args:
            connection_string (str): MongoDB connection string
        """
        try:
            self.client = pymongo.MongoClient(connection_string)
            self.db = self.client.Downloader  # Database name
            self.users_collection = self.db.users  # Collection name
            logging.info("MongoDB connection established successfully")
        except Exception as e:
            logging.error(f"MongoDB connection error: {e}")
            raise

    def store_user(self, user_id: int, username: str):
        """
        Store or update user information in MongoDB
        
        Args:
            user_id (int): Telegram user ID
            username (str): Telegram username
        """
        try:
            # Upsert operation: update if exists, insert if not
            self.users_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "user_id": user_id,
                    "username": username
                }},
                upsert=True
            )
            logging.info(f"User {user_id} recorded in database")
        except Exception as e:
            logging.error(f"Error storing user {user_id}: {e}")

class SpotifyDownloaderBot:
    def __init__(self, app):
        # Use the existing Pyrogram client
        self.app = app

        # Initialize Spotify API client
        self.spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id="c623bcd2b3024663b0c094b8dbbded1e",
            client_secret="b8fec0f24b014b18873078e1686f2f75"
        ))

        # Genius API credentials
        self.genius_token = "ftLPWvHrNZ6BbdM90RJrQsvPqAwcEB0YEp258QR8HwwHkeSbmdfZxUy5QS1BAyMH"
        self.genius_base_url = "https://api.genius.com"

    def search_spotify(self, query):
        """
        Search for a track on Spotify and return its metadata.
        """
        try:
            results = self.spotify.search(q=query, type='track', limit=1)
            if results['tracks']['items']:
                track = results['tracks']['items'][0]
                metadata = {
                    'name': track['name'],
                    'artists': ', '.join(artist['name'] for artist in track['artists']),
                    'album': track['album']['name'],
                    'url': track['external_urls']['spotify']
                }
                return metadata
            return None
        except Exception as e:
            logging.error(f"Spotify API error: {e}")
            return None

    def fetch_lyrics(self, track_name, artist_name):
        """
        Fetch lyrics using the Genius API.
        """
        try:
            search_url = f"{self.genius_base_url}/search"
            headers = {"Authorization": f"Bearer {self.genius_token}"}
            params = {"q": f"{track_name} {artist_name}"}

            response = requests.get(search_url, headers=headers, params=params)
            response.raise_for_status()
            results = response.json()

            # Find the first match for the song
            hits = results.get("response", {}).get("hits", [])
            if hits:
                song_url = hits[0]["result"]["url"]
                return f"Lyrics available here: [Genius Lyrics]({song_url})"
            else:
                return "Lyrics not found."
        except Exception as e:
            logging.error(f"Genius API error: {e}")
            return "Error fetching lyrics."

    def download_song(self, query, temp_dir):
        """
        Use yt-dlp to download a song as MP3 based on the query.
        Returns the path to the MP3 file.
        """
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(temp_dir / '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'cookiefile': 'cookies.txt',  # Include the cookies file
            'quiet': True,
            'no_warnings': True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch:{query}", download=True)
                output_file = ydl.prepare_filename(info['entries'][0])

                # Ensure the file is converted to MP3
                mp3_file = Path(output_file).with_suffix('.mp3')
                if mp3_file.exists():
                    return str(mp3_file)
                else:
                    logging.error("MP3 file conversion failed.")
                    return None
        except Exception as e:
            logging.error(f"yt-dlp error: {e}")
            return None

    def get_artist_songs(self, artist_name):
        """
        Fetch the list of top songs by an artist with Spotify links.
        """
        try:
            # Search for the artist
            results = self.spotify.search(q=f"artist:{artist_name}", type="artist", limit=1)
            if not results['artists']['items']:
                return None, "Artist not found."

            artist = results['artists']['items'][0]
            artist_id = artist['id']
            artist_name = artist['name']

            # Get the artist's top tracks
            top_tracks = self.spotify.artist_top_tracks(artist_id, country='US')['tracks']

            if not top_tracks:
                return None, f"No top tracks found for {artist_name}."

            # Format track list with Spotify links
            tracks = [f"{idx + 1}. {track['name']} ({track['album']['name']})  🔗 [Spotify Link]({track['external_urls']['spotify']})\n" 
                      for idx, track in enumerate(top_tracks)]

            return tracks, None
        except Exception as e:
            logging.error(f"Error fetching artist songs: {e}")
            return None, str(e)

    def add_spotify_handlers(self):
        """
        Add Spotify related command handlers to the main bot
        """
        @self.app.on_message(filters.command(["spotify"]))
        async def spotify_handler(client, message):
            # Ensure temporary directory exists
            temp_dir = Config.TEMP_DIR
            temp_dir.mkdir(exist_ok=True)

            query = ' '.join(message.command[1:]).strip()

            if not query:
                await message.reply_text("Please provide a song or artist name. Usage: /spotify <Song or Artist>")
                return

            # Initial processing message
            processing_msg = await message.reply_text("🔍 Searching for the track...")

            try:
                # Search for the track on Spotify
                metadata = self.search_spotify(query)
                if not metadata:
                    await processing_msg.edit_text("Could not find the track on Spotify.")
                    return

                # Update status to downloading
                await processing_msg.edit_text("⏬ Downloading track...")

                # Download the track using yt-dlp
                song_file = self.download_song(f"{metadata['name']} {metadata['artists']}", temp_dir)
                if not song_file:
                    await processing_msg.edit_text("Failed to download the track.")
                    return

                # Get file size for progress tracking
                file_size_bytes = os.path.getsize(song_file)

                # Create progress tracker
                progress_tracker = UploadProgressTracker(processing_msg, file_size_bytes)

                # Fetch lyrics from Genius API
                lyrics = self.fetch_lyrics(metadata['name'], metadata['artists'])

                # Prepare the track information
                track_info = (
                    f"🎵 **Track Found:** {metadata['name']}\n"
                    f"👤 **Artists:** {metadata['artists']}\n"
                    f"💽 **Album:** {metadata['album']}\n"
                    f"🔗 [Spotify Link]({metadata['url']})\n\n"
                    f"🎶 **Lyrics:**\n{lyrics}"
                )
                
                # Send the audio file with track information and progress tracking
                await client.send_audio(
                    chat_id=message.chat.id, 
                    audio=song_file, 
                    caption=track_info, 
                    progress=progress_tracker.progress_callback
                )

                # Delete the processing message
                await processing_msg.delete()

                # Cleanup the temporary file
                try:
                    os.remove(song_file)
                except Exception as e:
                    logger.error(f"Error removing file {song_file}: {e}")

            except Exception as e:
                logger.error(f"Spotify download error: {e}")
                await processing_msg.edit_text('An error occurred while processing your Spotify request.')

        @self.app.on_message(filters.command("sptfylist"))
        async def sptfylist_handler(client, message):
            artist_name = ' '.join(message.command[1:]).strip()

            if not artist_name:
                await message.reply_text("Please provide an artist name. Usage: /sptfylist <Artist>")
                return

            # Send the initial search message and store the reference
            status_message = await message.reply_text(f"Searching for songs by **{artist_name}**...")

            # Get artist songs
            tracks, error = self.get_artist_songs(artist_name)
            if error:
                await status_message.edit_text(f"Error: {error}")
                return

            # Send the list of songs by editing the original message
            track_list = "\n".join(tracks)
            await status_message.edit_text(f"**Top Tracks by {artist_name}:**\n\n{track_list}")

class MediaProcessor:
    @staticmethod
    def validate_and_process_media(media_info, default_caption='📸 Instagram Media', prefix='temp'):
        try:
            media_type = media_info.get('type')
            download_url = media_info.get('download_url')
            response = requests.get(download_url, stream=True)

            if response.status_code != 200 or int(response.headers.get('content-length', 0)) == 0:
                return None

            ext = {'video': 'mp4', 'image': 'jpg'}.get(media_type, 'media')
            temp_filename = os.path.join(Config.TEMP_DIR, f"{prefix}_media.{ext}")

            with open(temp_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            if media_type == 'video':
                return MediaProcessor._validate_video(temp_filename, media_info, default_caption)
            elif media_type == 'image':
                return MediaProcessor._validate_image(temp_filename, media_info, default_caption)
        except Exception as e:
            logger.error(f"Media processing error: {e}")
            return None

    @staticmethod
    def _validate_video(filename, media_info, default_caption):
        video = cv2.VideoCapture(filename)
        width, height, fps = int(video.get(cv2.CAP_PROP_FRAME_WIDTH)), int(video.get(cv2.CAP_PROP_FRAME_HEIGHT)), video.get(cv2.CAP_PROP_FPS)
        duration = video.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps > 0 else 0
        video.release()

        if width == 0 or height == 0 or duration == 0:
            os.remove(filename)
            return None

        return {'filename': filename, 'type': 'video', 'caption': media_info.get('caption', default_caption), 'duration': int(duration)}

    @staticmethod
    def _validate_image(filename, media_info, default_caption):
        try:
            img = Image.open(filename)
            img.verify()
            width, height = img.size
            if width == 0 or height == 0:
                os.remove(filename)
                return None
            return {'filename': filename, 'type': 'image', 'caption': media_info.get('caption', default_caption)}
        except:
            os.remove(filename)
            return None


class TwitterDownloader:
    def __init__(self, temp_dir: Path):
        """
        Initialize Twitter downloader with a temp directory
        
        Args:
            temp_dir (Path): Directory for temporary file storage
        """
        self.temp_dir = temp_dir
        # Configure yt-dlp to use the temp directory
        yt_dlp.utils.std_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

    def download_tweet_media(self, tweet_url: str) -> Tuple[List[str], List[str]]:
        """
        Download media from a tweet URL
        
        Args:
            tweet_url (str): URL of the tweet
        
        Returns:
            Tuple of lists containing downloaded file paths and their captions
        """
        # Ensure download directory exists
        self.temp_dir.mkdir(exist_ok=True)
        
        ydl_opts = {
            'outtmpl': os.path.join(str(self.temp_dir), '%(uploader)s_%(title).100s.%(ext)s'),
            'format': 'best',
            'no_warnings': True,
            'quiet': True,
            'no_color': True,
            'writesubtitles': True,
            'writeinfojson': True,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(tweet_url, download=True)
                
                downloaded_files = []
                captions = []
                
                # Handle multiple entries or single media
                entries = info.get('entries', [info])
                for entry in entries:
                    # Prepare media file
                    media_file = ydl.prepare_filename(entry)
                    downloaded_files.append(media_file)
                    
                    # Extract caption/description
                    raw_caption = entry.get('description', '') or entry.get('title', '')
                    
                    # Find embedded URLs (e.g., https://t.co/...)
                    embedded_url = re.search(r'https?://t\.co/\S+', raw_caption)
                    if embedded_url:
                        embedded_url = embedded_url.group(0)
                        # Remove the embedded URL from the caption
                        raw_caption = raw_caption.replace(embedded_url, '').strip()
                    else:
                        embedded_url = ''
                    
                    # Construct the caption
                    formatted_caption = (
                        f"Title: {raw_caption}\n"
                        f"Url For Check: {embedded_url}\n"
                        f"Platform: X"
                    )
                    captions.append(formatted_caption)
                
                return downloaded_files, captions
        except Exception as e:
            logger.error(f"Twitter download error: {e}")
            return [], []

    def cleanup_related_files(self, base_file_path: str):
        """
        Remove all related files (video, json, subtitles, etc.) 
        based on a base file path
        
        Args:
            base_file_path (str): Path to the base media file
        """
        try:
            # Get the directory and filename without extension
            file_dir = os.path.dirname(base_file_path)
            filename_without_ext = os.path.splitext(os.path.basename(base_file_path))[0]
            
            # Pattern to match all related files
            pattern = os.path.join(file_dir, f"{filename_without_ext}*")
            
            # Remove matching files
            for file in glob.glob(pattern):
                os.remove(file)
        except Exception as e:
            logger.error(f"Error during Twitter file cleanup: {e}")

@dataclass
class YouTubeMedia:
    url: str
    file_path: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[str] = None
    file_size: Optional[str] = None
    thumbnail_path: Optional[str] = None

class YouTubeDownloader:
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        # Suppress yt-dlp logging
        yt_dlp.utils.std_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

    async def download_video(self, url: str) -> Optional[dict]:
        """
        Download YouTube video
        
        Args:
            url (str): YouTube video URL
        
        Returns:
            Optional[dict]: Downloaded media information
        """
        # Ensure download directory exists
        self.temp_dir.mkdir(exist_ok=True)
        
        # Validate YouTube URL
        if not await validate_youtube_url(url):
            return None
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(str(self.temp_dir), '%(title)s.%(ext)s'),
            'quiet': True,
            'cookiefile': Config.YT_COOKIES_PATH,
            'no_warnings': True,
            'no_color': True,
            'simulate': False,
            'nooverwrites': True,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }]
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Capture video information 
                info_dict = ydl.extract_info(url, download=True)
                
                # Get the filename
                filename = ydl.prepare_filename(info_dict)
                
                # Extract title
                title = info_dict.get('title', os.path.basename(filename))
                
                # Get duration
                duration = await format_duration(info_dict.get('duration', 0))
                
                # Get file size
                file_path = filename
                file_size = await format_size(os.path.getsize(file_path)) if os.path.exists(file_path) else '0 B'
                
                # Prepare thumbnail
                thumbnail_url = info_dict.get('thumbnail')
                thumbnail_path = None
                if thumbnail_url:
                    sanitized_title = await sanitize_filename(title)
                    thumbnail_path = await prepare_thumbnail(thumbnail_url, os.path.join(str(self.temp_dir), sanitized_title))
                
                return {
                    'url': url,
                    'file_path': file_path,
                    'title': title,
                    'duration': duration,
                    'file_size': file_size,
                    'thumbnail_path': thumbnail_path
                }
        
        except Exception as e:
            logging.error(f"YouTube download error: {e}")
            return None
        
    async def download_audio(self, url: str) -> Optional[dict]:
        """
        Download YouTube audio as MP3
        
        Args:
            url (str): YouTube video URL
        
        Returns:
            Optional[dict]: Downloaded audio information
        """
        # Ensure download directory exists
        self.temp_dir.mkdir(exist_ok=True)
        
        # Validate YouTube URL
        if not await validate_youtube_url(url):
            return None
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(str(self.temp_dir), '%(title)s.%(ext)s'),
            'quiet': True,
            'cookiefile': Config.YT_COOKIES_PATH,
            'no_warnings': True,
            'no_color': True,
            'simulate': False,
            'nooverwrites': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Capture video information 
                info_dict = ydl.extract_info(url, download=True)
                
                # Get the filename
                filename = ydl.prepare_filename(info_dict)
                # Replace the original extension with .mp3
                filename = os.path.splitext(filename)[0] + '.mp3'
                
                # Extract title
                title = info_dict.get('title', os.path.basename(filename))
                
                # Get duration
                duration = await format_duration(info_dict.get('duration', 0))
                
                # Get file size
                file_path = filename
                file_size = await format_size(os.path.getsize(file_path)) if os.path.exists(file_path) else '0 B'
                
                # Prepare thumbnail
                thumbnail_url = info_dict.get('thumbnail')
                thumbnail_path = None
                if thumbnail_url:
                    sanitized_title = await sanitize_filename(title)
                    thumbnail_path = await prepare_thumbnail(thumbnail_url, os.path.join(str(self.temp_dir), sanitized_title))
                
                return {
                    'url': url,
                    'file_path': file_path,
                    'title': title,
                    'duration': duration,
                    'file_size': file_size,
                    'thumbnail_path': thumbnail_path
                }
        
        except Exception as e:
            logging.error(f"YouTube audio download error: {e}")
            return None
        
    async def search_youtube_audio(self, query: str) -> Optional[str]:
        """
        Search YouTube for the first audio result matching the query
        
        Args:
            query (str): Search term for the song/audio
        
        Returns:
            Optional[str]: First matching YouTube video URL or None
        """
        ydl_opts = {
            'format': 'bestaudio/best',
            'default_search': 'ytsearch1:',
            'nooverwrites': True,
            'cookiefile': Config.YT_COOKIES_PATH,
            'no_warnings': True,
            'quiet': True,
            'no_color': True,
            'simulate': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Perform the search
                info = ydl.extract_info(query, download=False)
                
                # Return the first result's URL
                if 'entries' in info and info['entries']:
                    return info['entries'][0]['webpage_url']
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
        
        return None

class UploadProgressTracker:
    def __init__(self, message: Message, total_size: int):
        """
        Initialize upload progress tracker
        
        Args:
            message (Message): Telegram message to edit with progress
            total_size (int): Total file size in bytes
        """
        self.message = message
        self.total_size = total_size
        self.last_update_time = 0
        self.min_update_interval = 2  # Minimum seconds between updates
        self.last_uploaded = 0

    def generate_progress_bar(self, current: int) -> str:
        """
        Generate a graphical progress bar
        
        Args:
            current (int): Current uploaded bytes
        
        Returns:
            str: Formatted progress bar
        """
        try:
            percentage = min(100, (current / self.total_size) * 100)
            filled_length = int(20 * current // self.total_size)
            bar = '▓' * filled_length + '░' * (20 - filled_length)
            
            # Calculate upload speed
            current_time = time.time()
            time_diff = current_time - self.last_update_time or 0.001
            speed = (current - self.last_uploaded) / time_diff / 1024 / 1024  # MB/s
            
            return (
                f"📥 ​🇺​​🇵​​🇱​​🇴​​🇦​​🇩​ ​🇵​​🇷​​🇴​​🇬​​🇷​​🇪​​🇸​​🇸​ 📥\n"
                f"{bar}\n"
                f"🚧 Pc: {percentage:.2f}%\n"
                f"⚡️ Speed: {speed:.2f} MB/s\n"
                f"📶 Status: {current/1024/1024:.1f} MB of {self.total_size/1024/1024:.2f} MB"
            )
        except Exception:
            return "Uploading..."

    async def progress_callback(self, current: int, total: int):
        """
        Progress callback for file upload
        
        Args:
            current (int): Current uploaded bytes
            total (int): Total file size in bytes
        """
        current_time = time.time()
        
        # Throttle updates to prevent excessive message edits
        if (current_time - self.last_update_time >= self.min_update_interval) or current == total:
            try:
                progress_text = self.generate_progress_bar(current)
                await self.message.edit_text(progress_text)
                
                # Update tracking variables
                self.last_update_time = current_time
                self.last_uploaded = current
            except Exception:
                pass  # Silently handle any update errors

@dataclass
class FacebookMedia:
    url: str
    file_path: Optional[str] = None
    title: Optional[str] = None
    media_type: str = 'video'

class FacebookDownloader:
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        # Suppress yt-dlp logging
        yt_dlp.utils.std_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

    def download_video(self, url: str) -> Optional[FacebookMedia]:
        """
        Download Facebook video or Reel
        
        Args:
            url (str): Facebook video URL
        
        Returns:
            Optional[FacebookMedia]: Downloaded media information
        """
        # Ensure download directory exists
        self.temp_dir.mkdir(exist_ok=True)
        
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(str(self.temp_dir), '%(title)s.%(ext)s'),
            'quiet': True,
            
            'no_warnings': True,
            'no_color': True,
            'simulate': False,
            'nooverwrites': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Capture video information 
                info_dict = ydl.extract_info(url, download=True)
                
                # Get the filename
                filename = ydl.prepare_filename(info_dict)
                
                # Extract title
                title = info_dict.get('title', os.path.basename(filename))
                
                # Verify file exists
                if os.path.exists(filename):
                    return FacebookMedia(
                        url=url, 
                        file_path=filename, 
                        title=title
                    )
                else:
                    return None
        
        except Exception as e:
            logging.error(f"Facebook download error: {e}")
            return None

        
@dataclass
class PinterestMedia:
    url: str = ''
    media_type: str = 'image'
    width: int = 0
    height: int = 0
    fallback_urls: list = field(default_factory=list)
    
    def __post_init__(self):
        if self.fallback_urls is None:
            self.fallback_urls = []

class PinterestDownloader:
    def __init__(self):
        self.session = None
        self.pin_patterns = [
            r'/pin/(\d+)',
            r'pin/(\d+)',
            r'pin_id=(\d+)'
        ]
        
    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(headers=Config.HEADERS)

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def extract_pin_id(self, url: str) -> Optional[str]:
        """Extract Pinterest pin ID from URL"""
        await self.init_session()
        
        if 'pin.it' in url:
            async with self.session.head(url, allow_redirects=True) as response:
                url = str(response.url)
        
        for pattern in self.pin_patterns:
            if match := re.search(pattern, url):
                return match.group(1)
        return None

    def get_highest_quality_image(self, image_url: str) -> str:
        """Convert image URL to highest quality version"""
        # Remove any existing dimensions and get original
        url = re.sub(r'/\d+x/|/\d+x\d+/', '/originals/', image_url)
        url = re.sub(r'\?.+$', '', url)  # Remove query parameters
        return url

    async def get_pin_data(self, pin_id: str) -> Optional[PinterestMedia]:
        """Get pin data using webpage method"""
        try:
            return await self.get_data_from_webpage(pin_id)
        except Exception as e:
            logger.error(f"Error getting pin data: {e}")
            return None

    async def get_data_from_api(self, pin_id: str) -> Optional[PinterestMedia]:
        """Get highest quality image data from Pinterest's API"""
        api_url = f"https://api.pinterest.com/v3/pidgets/pins/info/?pin_ids={pin_id}"
        
        async with self.session.get(api_url) as response:
            if response.status == 200:
                data = await response.json()
                if pin_data := data.get('data', [{}])[0].get('pin'):
                    # Check for video first
                    if videos := pin_data.get('videos', {}).get('video_list', {}):
                        video_formats = list(videos.values())
                        if video_formats:
                            best_video = max(video_formats, key=lambda x: x.get('width', 0) * x.get('height', 0))
                            return PinterestMedia(
                                url=best_video.get('url'),
                                media_type='video',
                                width=best_video.get('width', 0),
                                height=best_video.get('height', 0)
                            )
                    
                    # Get highest quality image
                    if images := pin_data.get('images', {}):
                        # Try to get original image first
                        if orig_image := images.get('orig'):
                            image_url = self.get_highest_quality_image(orig_image.get('url'))
                            return PinterestMedia(
                                url=image_url,
                                media_type='image',
                                width=orig_image.get('width', 0),
                                height=orig_image.get('height', 0)
                            )
        return None

    async def get_data_from_webpage(self, pin_id: str) -> Optional[PinterestMedia]:
        """Get media data from webpage with comprehensive parsing"""
        url = f"https://www.pinterest.com/pin/{pin_id}/"
        
        async with self.session.get(url) as response:
            if response.status == 200:
                text = await response.text()
                
                # Look for video first
                video_matches = re.findall(r'"url":"([^"]*?\.mp4[^"]*)"', text)
                if video_matches:
                    video_url = unquote(video_matches[0].replace('\\/', '/'))
                    return PinterestMedia(
                        url=video_url,
                        media_type='video'
                    )

                # Enhanced image URL extraction patterns
                image_patterns = [
                    # High resolution image patterns
                    r'"originImageUrl":"([^"]+)"',
                    r'"image":"([^"]+)"',
                    r'"imageUrl":"([^"]+)"',
                    r'<meta property="og:image" content="([^"]+)"',
                    r'"image_url":"([^"]+)"',
                    r'https://[^"]+?i\.pinimg\.com/originals/[^"]+',
                ]
                
                fallback_urls = []
                
                for pattern in image_patterns:
                    matches = re.findall(pattern, text)
                    for match in matches:
                        if match:
                            # Decode and normalize URL
                            image_url = unquote(match.replace('\\/', '/'))
                            
                            # Check for valid image extensions
                            if any(ext in image_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                                # Prioritize original resolution URLs
                                original_url = self.get_highest_quality_image(image_url)
                                
                                if original_url not in fallback_urls:
                                    fallback_urls.append(original_url)
                
                # If any URLs found, return the first one
                if fallback_urls:
                    return PinterestMedia(
                        url=fallback_urls[0],
                        media_type='image',
                        fallback_urls=fallback_urls[1:]  # Store other potential URLs
                    )

        return None

    async def get_data_from_mobile_api(self, pin_id: str) -> Optional[PinterestMedia]:
        """Get highest quality media from mobile API"""
        mobile_api_url = f"https://www.pinterest.com/_ngapi/pins/{pin_id}"
        
        headers = {**Config.HEADERS, 'Accept': 'application/json'}
        async with self.session.get(mobile_api_url, headers=headers) as response:
            if response.status == 200:
                try:
                    data = await response.json()
                    
                    # Check for video first
                    if video_data := data.get('videos', {}).get('video_list', {}):
                        best_video = max(
                            video_data.values(),
                            key=lambda x: x.get('width', 0) * x.get('height', 0)
                        )
                        if 'url' in best_video:
                            return PinterestMedia(
                                url=best_video['url'],
                                media_type='video',
                                width=best_video.get('width', 0),
                                height=best_video.get('height', 0)
                            )
                    
                    # Get highest quality image
                    if image_data := data.get('images', {}):
                        if orig_image := image_data.get('orig'):
                            image_url = self.get_highest_quality_image(orig_image.get('url'))
                            return PinterestMedia(
                                url=image_url,
                                media_type='image',
                                width=orig_image.get('width', 0),
                                height=orig_image.get('height', 0)
                            )
                except json.JSONDecodeError:
                    pass
        
        return None

class PinterestFacebookBot:
    def __init__(self):
        self.CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
        # Initialize Pyrogram Client
        self.app = Client(
            "media_downloader_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        self.mongo_connection = MongoDBConnection(os.getenv("MONGO_URL"))
        
        # Initialize downloaders
        self.downloader = PinterestDownloader()
        self.facebook_downloader = FacebookDownloader(Config.TEMP_DIR)
        self.youtube_downloader = YouTubeDownloader(Config.TEMP_DIR)
        self.twitter_downloader = TwitterDownloader(Config.TEMP_DIR)
        self.spotify_downloader = SpotifyDownloaderBot(self.app)
        # Set up event handlers
        self.setup_handlers()

    def setup_handlers(self):
        """Set up message event handlers"""
        self.spotify_downloader.add_spotify_handlers()
        # Existing start command handler...
        @self.app.on_message(filters.command(["start"]))
        async def start_command(client: Client, message: Message):
            """Handle /start command with channel membership check"""
            try:
                # Check if user is a member of the channel
                is_member = await self.check_channel_membership(client, message.from_user.id)
                
                # Get the user's first name or use 'User' if not available
                user_first_name = message.from_user.first_name if message.from_user else 'User'
                
                if is_member:
                    # User is a member, show welcome message
                    await self.send_welcome_message(client, message)
                else:
                    # User is not a member, show channel join message
                    await self.send_channel_membership_message(client, message)
                
                # Store user information in MongoDB
                if message.from_user:
                    self.mongo_connection.store_user(
                        user_id=message.from_user.id, 
                        username=message.from_user.username or user_first_name
                    )
            
            except Exception as e:
                logger.error(f"Error in start command: {e}")
                await message.reply_text("An error occurred. Please try again later.")

        @self.app.on_callback_query(filters.regex("^check_membership$"))
        async def check_membership_callback(client: Client, callback_query: CallbackQuery):
            """Handle membership check callback"""
            try:
                is_member = await self.check_channel_membership(client, callback_query.from_user.id)
                
                if is_member:
                    # User is now a member
                    await callback_query.answer("✅ ᴍᴇᴍʙᴇʀꜱʜɪᴘ ᴠᴇʀɪꜰɪᴇᴅ! ʏᴏᴜ ᴄᴀɴ ɴᴏᴡ ᴜꜱᴇ ᴛʜᴇ ʙᴏᴛ.")
                    
                    # Get user's first name or use 'User'
                    user_first_name = callback_query.from_user.first_name or 'User'
                    
                    # Create welcome keyboard 
                    keyboard = InlineKeyboardMarkup([
                        [  # First row
                            InlineKeyboardButton("Join Channel", url="https://t.me/abir_x_official")
                        ],
                        [  # Second row
                            InlineKeyboardButton("👑 Owner", url="https://t.me/abirxdhackz"),
                            InlineKeyboardButton("➕ Add to Group", url="https://t.me/{Your Bot Username }?startgroup=true")
                        ]
                    ])
                    
                    # Welcome text
                    welcome_text = f'''🔥 **Welcome, [{user_first_name}](tg://user?id={callback_query.from_user.id})!**\n
❝𝐑𝐞𝐚𝐝𝐲 𝐭𝐨 𝐝𝐨𝐰𝐧𝐥𝐨𝐚𝐝 𝐲𝐨𝐮𝐫 𝐟𝐚𝐯𝐨𝐫𝐢𝐭𝐞 𝐦𝐞𝐝𝐢𝐚? 🎉❞                                       
𝙹𝚞𝚜𝚝 𝚜𝚎𝚗𝚍 𝚖𝚎 𝚊 𝚕𝚒𝚗𝚔, 𝚊𝚗𝚍 𝙸'𝚕𝚕 𝚝𝚊𝚔𝚎 𝚌𝚊𝚛𝚎 𝚘𝚏 𝚒𝚝 𝚏𝚘𝚛 𝚢𝚘𝚞❣\n
ⓕ **𝗙𝗮𝗰𝗲𝗯𝗼𝗼𝗸** : ᴠɪᴅᴇᴏꜱ ᴀɴᴅ ʀᴇᴇʟꜱ
📌 **𝗣𝗶𝗻𝘁𝗲𝗿𝗲𝘀𝘁** : ɪᴍᴀɢᴇꜱ ᴀɴᴅ ᴠɪᴅᴇᴏꜱ
▶️ **𝗬𝗼𝘂𝗧𝘂𝗯𝗲** : ​ᴠɪᴅᴇᴏ ᴀɴᴅ ᴀᴜᴅɪᴏ​(​/audio ɴᴀᴍᴇ ᴏʀ ᴜʀʟ​)
Ⓧ **𝗫/𝗧𝘄𝗶𝘁𝘁𝗲𝗿** : ᴠɪᴅᴇᴏꜱ ᴀɴᴅ ᴍᴇᴅɪᴀ
Ⓘ **𝗜𝗻𝘀𝘁𝗮𝗴𝗿𝗮𝗺** : ʀᴇᴇʟꜱ, ᴘᴏꜱᴛꜱ, ɪɢᴛᴠ, ꜱᴛᴏʀɪᴇꜱ, ʜɪɢʜʟɪɢʜᴛꜱ ᴀɴᴅ ᴠɪᴅᴇᴏꜱ
♫♪ **𝗦𝗽𝗼𝘁𝗶𝗳𝘆** : ᴅᴏᴡɴʟᴏᴀᴅ ꜱᴘᴏᴛɪꜰʏ ᴛʀᴀᴄᴋ (/Spotify And /Sptfylist)\n
 **Send a link now to start downloading!**
 ♥ ʙᴏᴛ ᴄᴀɴ ᴡᴏʀᴋ ꜰᴏʀ ɢʀᴏᴜᴘ ᴛ๏๏! ♥ '''
                    
                    try:
                        # Send a new animation to replace the existing message
                        await client.send_animation(
                            chat_id=callback_query.message.chat.id,
                            animation="https://cdn.glitch.global/8165267b-e8d9-4a47-a5f2-bc40cef0b65f/loading-15146_512.gif?v=1733936190678",
                            caption=welcome_text,
                            parse_mode=enums.ParseMode.MARKDOWN,
                            reply_markup=keyboard
                        )
                        
                        # Delete the original membership message
                        await callback_query.message.delete()
                    
                    except Exception as e:
                        logger.error(f"Error sending welcome animation: {e}")
                        
                        # Fallback to sending text message if animation fails
                        await callback_query.message.edit_text(
                            text=welcome_text,
                            parse_mode=enums.ParseMode.MARKDOWN,
                            reply_markup=keyboard
                        )
                else:
                    # User still hasn't joined
                    await callback_query.answer("🚫 ᴘʟᴇᴀꜱᴇ ᴊᴏɪɴ ᴛʜᴇ ᴄʜᴀɴɴᴇʟ ꜰɪʀꜱᴛ!", show_alert=True)
            
            except Exception as e:
                logger.error(f"Error in membership check: {e}")
                await callback_query.answer("An error occurred. Please try again.")

        @self.app.on_message(
                filters.text & 
                filters.regex(r"(pinterest\.com|pin\.it|facebook\.com|youtube\.com|instagram\.com/(reel/|p/|stories/|s/aGlnaGxpZ2h0).*?|youtu\.be|(?:twitter|x)\.com/\w+/status/\d+)") &
                ~filters.command([])
            )
        async def handle_url_download(client: Client, message: Message):
            """Centralized URL handling method with channel membership check"""
            try:
                # Check channel membership
                is_member = await self.check_channel_membership(client, message.from_user.id)
                
                if not is_member:
                    # If not a member, send channel membership message
                    await self.send_channel_membership_message(client, message)
                    return
                
                # Existing URL handling logic (rest of the code remains the same)
                url = message.text.strip()
                
                # Send initial processing message
                processing_msg = await message.reply_text("⏳ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ʀᴇQᴜᴇꜱᴛ...")
                
                if 'pinterest.com' in url or 'pin.it' in url:
                    await self.download_pinterest(client, message, processing_msg)
                elif 'facebook.com' in url:
                    await self.download_facebook(client, message, processing_msg)
                elif 'youtube.com' in url or 'youtu.be' in url:
                    await self.download_youtube(client, message, processing_msg)
                elif re.search(r'(?:twitter|x)\.com/\w+/status/\d+', url):
                    await self.download_twitter(client, message, processing_msg)
                elif 'instagram.com' in url:
                    await self.download_instagram(client, message, processing_msg)
                else:
                    await processing_msg.edit_text('Unsupported link type')
                
            except Exception as e:
                logger.error(f"Error handling URL: {e}")
                await processing_msg.edit_text('ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ʀᴇQᴜᴇꜱᴛ.')

        
        @self.app.on_message(filters.command(["audio"]))
        async def handle_audio_download(client: Client, message: Message):
            """Handle audio download requests"""
            # Send initial processing message
            processing_msg = await message.reply_text("⏳ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ᴀᴜᴅɪᴏ ʀᴇQᴜᴇꜱᴛ...")
            
            try:
                await self.download_youtube_audio(client, message, processing_msg)
            except Exception as e:
                logger.error(f"Error in audio download handler: {e}")
                await processing_msg.edit_text('ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ʀᴇQᴜᴇꜱᴛ.')

        

        @self.app.on_message(filters.command(["broadcast"]) & filters.user(Config.ADMIN_USER_IDS))
        async def broadcast_command(client: Client, message: Message):
            """Handle broadcast command for admins"""
            # Check if the message is a reply
            if not message.reply_to_message:
                await message.reply_text("ᴘʟᴇᴀꜱᴇ ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ.")
                return

            # Send initial broadcast status
            broadcast_status_msg = await message.reply_text("🔄 ​🇵​​🇷​​🇪​​🇵​​🇦​​🇷​​🇮​​🇳​​🇬​ ​🇧​​🇷​​🇴​​🇦​​🇩​​🇨​​🇦​​🇸​​🇹​...")
            
            try:
                # Fetch all users from MongoDB
                users = list(self.mongo_connection.users_collection.find())
                total_users = len(users)
                
                # Prepare broadcast message details
                broadcast_message = message.reply_to_message
                
                # Initialize progress tracking
                successful_sends = 0
                failed_sends = 0
                
                # Progress bar update interval
                update_interval = max(1, total_users // 10)  # Update every 10% progress
                
                # Broadcast to all users
                for index, user_data in enumerate(users, 1):
                    try:
                        # Broadcast according to message type
                        await self.send_broadcast_message(
                            client, 
                            user_data['user_id'], 
                            broadcast_message
                        )
                        successful_sends += 1
                    except Exception as e:
                        failed_sends += 1
                        logging.error(f"Failed to send broadcast to {user_data['user_id']}: {e}")
                    
                    # Update progress periodically
                    if index % update_interval == 0:
                        progress_percentage = (index / total_users) * 100
                        progress_bar = self.generate_progress_bar(progress_percentage)
                        await broadcast_status_msg.edit_text(
                            f"📡 *Broadcast Progress*\n\n"
                            f"{progress_bar}\n\n"
                            f"✅ Sent: {successful_sends}\n"
                            f"❌ Failed: {failed_sends}\n"
                            f"👥 Total Users: {total_users}"
                        )
                
                # Final status update
                await broadcast_status_msg.edit_text(
                    f"🎉 *Broadcast Completed*\n\n"
                    f"✅ Successfully sent to: {successful_sends} users\n"
                    f"❌ Failed to send to: {failed_sends} users\n"
                    f"👥 Total Users: {total_users}"
                )
            
            except Exception as e:
                await broadcast_status_msg.edit_text(f"❌ Broadcast failed: {str(e)}")

    async def send_broadcast_message(self, client: Client, user_id: int, message: Message):
        """
        Send broadcast message with support for different message types
        
        Args:
            client (Client): Pyrogram client
            user_id (int): Telegram user ID
            message (Message): Original message to broadcast
        """
        # Handle text message
        if message.text:
            await client.send_message(
                chat_id=user_id, 
                text=message.text,
                entities=message.entities
            )
            return

        # Handle photo
        if message.photo:
            photo = await message.download()
            try:
                await client.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=message.caption,
                    caption_entities=message.caption_entities
                )
            finally:
                os.remove(photo)
            return

        # Handle video
        if message.video:
            video = await message.download()
            try:
                await client.send_video(
                    chat_id=user_id,
                    video=video,
                    caption=message.caption,
                    caption_entities=message.caption_entities
                )
            finally:
                os.remove(video)
            return

        # Handle document
        if message.document:
            document = await message.download()
            try:
                await client.send_document(
                    chat_id=user_id,
                    document=document,
                    caption=message.caption,
                    caption_entities=message.caption_entities
                )
            finally:
                os.remove(document)
            return

        # Handle audio
        if message.audio:
            audio = await message.download()
            try:
                await client.send_audio(
                    chat_id=user_id,
                    audio=audio,
                    caption=message.caption,
                    caption_entities=message.caption_entities
                )
            finally:
                os.remove(audio)
            return

        # Handle any inline keyboard
        if message.reply_markup:
            # Convert Telegram inline keyboard to Pyrogram inline keyboard
            if isinstance(message.reply_markup, InlineKeyboardMarkup):
                keyboard_buttons = []
                for row in message.reply_markup.inline_keyboard:
                    keyboard_row = []
                    for button in row:
                        keyboard_row.append(
                            PyrogramInlineKeyboardButton(
                                button.text, 
                                url=button.url
                            )
                        )
                    keyboard_buttons.append(keyboard_row)
                
                # Send message with inline keyboard
                await client.send_message(
                    chat_id=user_id,
                    text=message.text or message.caption or "Broadcast Message",
                    reply_markup=PyrogramInlineKeyboardMarkup(keyboard_buttons)
                )
            return

    def generate_progress_bar(self, percentage: float, width: int = 20) -> str:
        """
        Generate a text-based progress bar
        
        Args:
            percentage (float): Percentage of progress (0-100)
            width (int): Width of the progress bar
        
        Returns:
            str: Formatted progress bar
        """
        filled_length = int(width * percentage / 100)
        bar = '▓' * filled_length + '░' * (width - filled_length)
        return f"[{bar}] {percentage:.1f}%"

    async def check_channel_membership(self, client: Client, user_id: int) -> bool:
        """
        Check if the user is a member of the specified channel
        
        Args:
            client (Client): Pyrogram client
            user_id (int): User's Telegram ID
        
        Returns:
            bool: True if user is a member, False otherwise
        """
        try:
            # Get user's membership status
            chat_member = await client.get_chat_member(
                chat_id=f"@{self.CHANNEL_USERNAME}", 
                user_id=user_id
            )
            
            # Check if user is an active member
            return chat_member.status in [
                enums.ChatMemberStatus.MEMBER, 
                enums.ChatMemberStatus.ADMINISTRATOR, 
                enums.ChatMemberStatus.OWNER
            ]
        except Exception as e:
            logger.error(f"Membership check error: {e}")
            return False

    async def send_channel_membership_message(self, client: Client, message: Message):
        """
        Send channel membership required message
        
        Args:
            client (Client): Pyrogram client
            message (Message): Original message
        """
        # Create inline keyboard for channel join and membership check
        keyboard = InlineKeyboardMarkup([
            [  # First row
                InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{self.CHANNEL_USERNAME}")
            ],
            [  # Second row
                InlineKeyboardButton("🔍 Check Membership", callback_data="check_membership")
            ]
        ])
        
        # Membership required message
        membership_text = f'''🔒 **𝗖𝗵𝗮𝗻𝗻𝗲𝗹 𝗠𝗲𝗺𝗯𝗲𝗿𝘀𝗵𝗶𝗽 𝗥𝗲𝗾𝘂𝗶𝗿𝗲𝗱**\n
- ᴊᴏɪɴ @{self.CHANNEL_USERNAME} ᴛᴏ ᴜꜱᴇ ᴛʜᴇ ʙᴏᴛ
- ᴄʟɪᴄᴋ "✅ ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ" ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ
- ᴀꜰᴛᴇʀ ᴊᴏɪɴɪɴɢ, ᴄʟɪᴄᴋ ᴏɴ "🔍 ᴄʜᴇᴄᴋ ᴍᴇᴍʙᴇʀꜱʜɪᴘ" ʙᴜᴛᴛᴏɴ'''
        
        # Send membership message
        await message.reply_text(
            membership_text, 
            reply_markup=keyboard
        )

    async def send_welcome_message(self, client: Client, message: Message, user_first_name: Optional[str] = None):
        """
        Send welcome message to the user
        
        Args:
            client (Client): Pyrogram client
            message (Message): Original message
            user_first_name (Optional[str]): User's first name
        """
        # Use message's user first name or fallback to provided name or 'User'
        user_first_name = (
            message.from_user.first_name if message.from_user 
            else (user_first_name or 'User')
        )
        
        # Create welcome keyboard 
        keyboard = InlineKeyboardMarkup([
            [  # First row
                InlineKeyboardButton("Join Channel", url="https://t.me/abir_x_official")
            ],
            [  # Second row
                InlineKeyboardButton("👑 Owner", url="https://t.me/abirxdhackz"),
                InlineKeyboardButton("➕ Add to Group", url="https://t.me/{Your Bot Username}?startgroup=true")
            ]
        ])
        
        # Welcome text
        welcome_text = f'''🔥 **Welcome, [{user_first_name}](tg://user?id={message.from_user.id})!**\n
❝𝐑𝐞𝐚𝐝𝐲 𝐭𝐨 𝐝𝐨𝐰𝐧𝐥𝐨𝐚𝐝 𝐲𝐨𝐮𝐫 𝐟𝐚𝐯𝐨𝐫𝐢𝐭𝐞 𝐦𝐞𝐝𝐢𝐚? 🎉❞                                       
𝙹𝚞𝚜𝚝 𝚜𝚎𝚗𝚍 𝚖𝚎 𝚊 𝚕𝚒𝚗𝚔, 𝚊𝚗𝚍 𝙸'𝚕𝚕 𝚝𝚊𝚔𝚎 𝚌𝚊𝚛𝚎 𝚘𝚏 𝚒𝚝 𝚏𝚘𝚛 𝚢𝚘𝚞❣\n
ⓕ  **𝗙𝗮𝗰𝗲𝗯𝗼𝗼𝗸** : ᴠɪᴅᴇᴏꜱ ᴀɴᴅ ʀᴇᴇʟꜱ
📌 **𝗣𝗶𝗻𝘁𝗲𝗿𝗲𝘀𝘁** : ɪᴍᴀɢᴇꜱ ᴀɴᴅ ᴠɪᴅᴇᴏꜱ
▶️ **𝗬𝗼𝘂𝗧𝘂𝗯𝗲** : ​ᴠɪᴅᴇᴏ ᴀɴᴅ ᴀᴜᴅɪᴏ​(​/audio ɴᴀᴍᴇ ᴏʀ ᴜʀʟ​)
Ⓧ  **𝗫/𝗧𝘄𝗶𝘁𝘁𝗲𝗿** : ᴠɪᴅᴇᴏꜱ ᴀɴᴅ ᴍᴇᴅɪᴀ
Ⓘ  **𝗜𝗻𝘀𝘁𝗮𝗴𝗿𝗮𝗺** : ʀᴇᴇʟꜱ, ᴘᴏꜱᴛꜱ, ɪɢᴛᴠ, ꜱᴛᴏʀɪᴇꜱ, ʜɪɢʜʟɪɢʜᴛꜱ ᴀɴᴅ ᴠɪᴅᴇᴏꜱ
♫♪  **𝗦𝗽𝗼𝘁𝗶𝗳𝘆** : ᴅᴏᴡɴʟᴏᴀᴅ ꜱᴘᴏᴛɪꜰʏ ᴛʀᴀᴄᴋ (/Spotify And /Sptfylist)\n
 **Send a link now to start downloading!**
♥ ʙᴏᴛ ᴄᴀɴ ᴡᴏʀᴋ ꜰᴏʀ ɢʀᴏᴜᴘ ᴛ๏๏! ♥ '''
        
        try:
            # Send the animation (GIF) first
            await client.send_animation(
                chat_id=message.chat.id,
                animation="https://cdn.glitch.global/8165267b-e8d9-4a47-a5f2-bc40cef0b65f/loading-15146_512.gif?v=1733936190678",
                caption=welcome_text,
                reply_markup=keyboard
            )
        except Exception as e:
            # If sending animation fails, send text message as fallback
            logger.error(f"Error sending animation: {e}")
            await message.reply_text(
                welcome_text, 
                reply_markup=keyboard
            )

    # New method for YouTube download
    async def download_youtube(self, client: Client, message: Message, processing_msg: Message):
        """Handle YouTube URL messages with Pyrogram upload and progress tracking"""
        url = message.text.strip()
        
        try:
            await processing_msg.edit_text("⏳ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ʏᴏᴜᴛᴜʙᴇ ᴠɪᴅᴇᴏ...")
            
            # Download video
            result = await self.youtube_downloader.download_video(url)
            
            if not result:
                await processing_msg.edit_text('ᴄᴏᴜʟᴅ ɴᴏᴛ ᴅᴏᴡɴʟᴏᴀᴅ ᴍᴇᴅɪᴀ ꜰʀᴏᴍ ᴛʜɪꜱ ʏᴏᴜᴛᴜʙᴇ ʟɪɴᴋ.')
                return
            
            video_path = result['file_path']
            title = result['title']
            duration = result['duration']
            file_size = result['file_size']
            thumbnail_path = result.get('thumbnail_path')

            # Get actual file size
            file_size_bytes = os.path.getsize(video_path)

            # Generate caption for the video
            video_caption = (
                f"🎥 **{title}**\n"
                f"⏱ **Duration:** {duration}\n"
                f"📦 **Size:** {file_size}"
            )
            
            # Create progress tracker
            progress_tracker = UploadProgressTracker(processing_msg, file_size_bytes)
            
            # Upload video with progress
            await client.send_video(
                chat_id=message.chat.id,
                video=video_path,
                caption=video_caption,
                supports_streaming=True,
                thumb=thumbnail_path,
                progress=progress_tracker.progress_callback
            )
            
            # Cleanup
            if os.path.exists(video_path):
                os.remove(video_path)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            
            # Delete processing message
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"Error processing YouTube message: {e}")
            await processing_msg.edit_text('ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ʀᴇQᴜᴇꜱᴛ.')

    async def download_youtube_audio(self, client: Client, message: Message, processing_msg: Message):
        """Handle YouTube audio download requests"""
        query = message.text.split(' ', 1)[1].strip() if len(message.text.split()) > 1 else None
        
        if not query:
            await processing_msg.edit_text('ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ꜱᴏɴɢ ɴᴀᴍᴇ ᴏʀ ʏᴏᴜᴛᴜʙᴇ ᴜʀʟ ᴀꜰᴛᴇʀ /ᴀᴜᴅɪᴏ')
            return
        
        try:
            await processing_msg.edit_text("🔍 ꜱᴇᴀʀᴄʜɪɴɢ ꜰᴏʀ ᴀᴜᴅɪᴏ...")
            
            # Check if the query is already a valid YouTube URL
            if await validate_youtube_url(query):
                url = query
            else:
                # Perform YouTube search using the class method with correct reference
                url = await self.youtube_downloader.search_youtube_audio(query)
                
                if not url:
                    await processing_msg.edit_text('ᴄᴏᴜʟᴅ ɴᴏᴛ ꜰɪɴᴅ ᴀɴʏ ᴀᴜᴅɪᴏ ᴍᴀᴛᴄʜɪɴɢ ʏᴏᴜʀ ꜱᴇᴀʀᴄʜ.')
                    return
            
            await processing_msg.edit_text("⏳ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ᴀᴜᴅɪᴏ ᴅᴏᴡɴʟᴏᴀᴅ...")
            
            # Download audio
            result = await self.youtube_downloader.download_audio(url)
            
            if not result:
                await processing_msg.edit_text('ᴄᴏᴜʟᴅ ɴᴏᴛ ᴅᴏᴡɴʟᴏᴀᴅ ᴀᴜᴅɪᴏ ꜰʀᴏᴍ ᴛʜɪꜱ ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛ.')
                return
            
            audio_path = result['file_path']
            title = result['title']
            duration = result['duration']
            file_size = result['file_size']
            thumbnail_path = result.get('thumbnail_path')

            # Get actual file size
            file_size_bytes = os.path.getsize(audio_path)

            # Generate caption for the audio
            audio_caption = (
                f"🎵 **{title}**\n"
                f"⏱ **Duration:** {duration}\n"
                f"📦 **Size:** {file_size}"
            )
            
            # Create progress tracker
            progress_tracker = UploadProgressTracker(processing_msg, file_size_bytes)
            
            # Upload audio with progress
            await client.send_audio(
                chat_id=message.chat.id,
                audio=audio_path,
                caption=audio_caption,
                thumb=thumbnail_path,
                progress=progress_tracker.progress_callback
            )
            
            # Cleanup
            if os.path.exists(audio_path):
                os.remove(audio_path)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            
            # Delete processing message
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"Error processing YouTube audio message: {e}")
            await processing_msg.edit_text('An error occurred while processing your request.')


    async def download_facebook(self, client: Client, message: Message, processing_msg: Message):
        """Handle Facebook URL messages with Pyrogram upload and progress tracking"""
        url = message.text.strip()
        
        try:
            await processing_msg.edit_text("⏳ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ꜰᴀᴄᴇʙᴏᴏᴋ ᴠɪᴅᴇᴏ...")
            
            # Download video in a separate thread
            def download_media():
                return self.facebook_downloader.download_video(url)
            
            media_data = await asyncio.to_thread(download_media)
            
            if not media_data or not media_data.file_path:
                await processing_msg.edit_text('ᴄᴏᴜʟᴅ ɴᴏᴛ ᴅᴏᴡɴʟᴏᴀᴅ ᴍᴇᴅɪᴀ ꜰʀᴏᴍ ᴛʜɪꜱ ꜰᴀᴄᴇʙᴏᴏᴋ ʟɪɴᴋ.')
                return
            
            # Get actual file size
            file_size_bytes = os.path.getsize(media_data.file_path)

            # Create progress tracker
            progress_tracker = UploadProgressTracker(processing_msg, file_size_bytes)
            
            # Upload video using Pyrogram's send_video method with progress tracking
            await client.send_video(
                chat_id=message.chat.id,
                video=media_data.file_path,
                caption=f"Title: {media_data.title}" if media_data.title else None,
                supports_streaming=True,
                progress=progress_tracker.progress_callback
            )
            
            # Delete processing message
            await processing_msg.delete()
            
            # Cleanup
            os.remove(media_data.file_path)
            
        except Exception as e:
            logger.error(f"Error processing Facebook message: {e}")
            await processing_msg.edit_text('ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ʀᴇQᴜᴇꜱᴛ.')

    async def download_twitter(self, client: Client, message: Message, processing_msg: Message):
        """Handle Twitter/X URL messages with Pyrogram upload and progress tracking"""
        url = message.text.strip()
        
        try:
            await processing_msg.edit_text("⏳ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ x/ᴛᴡɪᴛᴛᴇʀ ᴍᴇᴅɪᴀ...")
            
            # Download media in a separate thread
            def download_media():
                return self.twitter_downloader.download_tweet_media(url)
            
            media_files, captions = await asyncio.to_thread(download_media)
            
            if not media_files:
                await processing_msg.edit_text('ᴄᴏᴜʟᴅ ɴᴏᴛ ᴅᴏᴡɴʟᴏᴀᴅ ᴍᴇᴅɪᴀ ꜰʀᴏᴍ ᴛʜɪꜱ x/ᴛᴡɪᴛᴛᴇʀ ʟɪɴᴋ.')
                return
            
            # Send and cleanup each media file
            for file_path, caption in zip(media_files, captions):
                try:
                    # Get actual file size
                    file_size_bytes = os.path.getsize(file_path)
                    
                    # Create progress tracker
                    progress_tracker = UploadProgressTracker(processing_msg, file_size_bytes)
                    
                    # Check media type and send accordingly
                    if file_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                        await client.send_video(
                            chat_id=message.chat.id,
                            video=file_path,
                            caption=caption,
                            supports_streaming=True,
                            progress=progress_tracker.progress_callback
                        )
                    else:
                        await client.send_document(
                            chat_id=message.chat.id,
                            document=file_path,
                            caption=caption,
                            progress=progress_tracker.progress_callback
                        )
                    
                    # Cleanup related files after successful upload
                    self.twitter_downloader.cleanup_related_files(file_path)
                
                except Exception as e:
                    logger.error(f"Error sending Twitter media: {e}")
                    await processing_msg.edit_text('ꜰᴀɪʟᴇᴅ ᴛᴏ ꜱᴇɴᴅ ᴍᴇᴅɪᴀ. ᴘʟᴇᴀꜱᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.')
            
            # Delete processing message
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"Error processing Twitter message: {e}")
            await processing_msg.edit_text('ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ʀᴇQᴜᴇꜱᴛ.')

    def download_instagram_media(self, url):
        """Download Instagram media using RapidAPI"""
        try:
            response = requests.get(
                Config.RAPID_API_URL, 
                headers=Config.RAPID_API_HEADERS, 
                params={"url": url}
            )
            data = response.json()
            if data.get('error', True):
                return "Unable to download media"

            media_type = 'carousel' if data.get('type') == 'album' else 'single'
            return MediaProcessor.validate_and_process_media(data) if media_type == 'single' else self._process_multiple_media(data)
        except Exception as e:
            logger.error(f"Instagram download error: {e}")
            return "Error occurred while downloading media"

    def _process_multiple_media(self, data):
        """Process multiple media items"""
        processed_media = []
        for index, media_info in enumerate(data.get('medias', [])):
            processed_item = MediaProcessor.validate_and_process_media(media_info, prefix=f"temp_media_{index}")
            if processed_item:
                processed_media.append(processed_item)
        return processed_media

    async def download_instagram(self, client: Client, message: Message, processing_msg: Message):
        """Handle Instagram URL messages"""
        url = message.text.strip()

        try:
            await processing_msg.edit_text("🔄 ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ɪɴꜱᴛᴀɢʀᴀᴍ ᴍᴇᴅɪᴀ...")
            result = await asyncio.to_thread(self.download_instagram_media, url)

            await processing_msg.edit_text("📤 ᴜᴘʟᴏᴀᴅɪɴɢ ᴍᴇᴅɪᴀ...")

            if isinstance(result, dict):
                await self._send_single_media(client, message, result)
            elif isinstance(result, list):
                await self._send_multiple_media_group(client, message, result)
            else:
                await processing_msg.edit_text(result)

            # Delete the processing message after sending media
            await processing_msg.delete()

        except Exception as e:
            logger.error(f"Instagram download error: {e}")
            await processing_msg.edit_text(f"❌ Error: {str(e)}")

    async def _send_single_media(self, client: Client, message: Message, media_info: dict):
        """Send a single media item"""
        try:
            if media_info['type'] == 'video':
                await client.send_video(
                    chat_id=message.chat.id, 
                    video=media_info['filename'], 
                    caption=media_info['caption']
                    
                )
            elif media_info['type'] == 'image':
                await client.send_photo(
                    chat_id=message.chat.id, 
                    photo=media_info['filename'], 
                    caption=media_info['caption']
                )
            
            # Delete the file after sending
            if os.path.exists(media_info['filename']):
                os.remove(media_info['filename'])
        except Exception as e:
            logger.error(f"Error sending single media: {e}")
            await message.reply_text(f"❌ Could not send media: {e}")

    async def _send_multiple_media_group(self, client: Client, message: Message, media_items: list):
        """Send multiple media items as a group"""
        media_group = []
        for item in media_items:
            try:
                if item['type'] == 'video':
                    media_group.append(
                        pyrogram.types.InputMediaVideo(
                            media=item['filename'], 
                            caption=item['caption'] if len(media_group) == 0 else None
                        )
                    )
                elif item['type'] == 'image':
                    media_group.append(
                        pyrogram.types.InputMediaPhoto(
                            media=item['filename'], 
                            caption=item['caption'] if len(media_group) == 0 else None
                        )
                    )
            except Exception as e:
                logger.error(f"Error preparing media group: {e}")

        if media_group:
            try:
                # Try sending as media group
                await client.send_media_group(chat_id=message.chat.id, media=media_group)
            except (FloodWait, MediaEmpty) as e:
                logger.error(f"Media send error: {e}")
                # Fallback to sending individually
                for item in media_items:
                    await self._send_single_media(client, message, item)

            # Clean up files
            for item in media_items:
                if os.path.exists(item['filename']):
                    os.remove(item['filename'])

    async def download_pinterest(self, client: Client, message: Message, processing_msg: Message):
        """Handle Pinterest URL messages with Pyrogram upload and progress tracking"""
        url = message.text.strip()
        
        try:
            # Ensure async session is initialized
            await self.downloader.init_session()
            
            # Extract pin ID
            pin_id = await self.downloader.extract_pin_id(url)
            if not pin_id:
                await processing_msg.edit_text('ɪɴᴠᴀʟɪᴅ ᴘɪɴᴛᴇʀᴇꜱᴛ ᴜʀʟ. ᴘʟᴇᴀꜱᴇ ꜱᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴘɪɴ ᴜʀʟ.')
                return
            
            # Get media data
            media_data = await self.downloader.get_pin_data(pin_id)
            if not media_data:
                await processing_msg.edit_text('🇨​​🇴​​🇺​​🇱​​🇩​ ​🇳​​🇴​​🇹​ ​🇫​​🇮​​🇳​​🇩​ ​🇲​​🇪​​🇩​​🇮​​🇦​ ​🇮​​🇳​ ​🇹​​🇭​​🇮​​🇸​ ​🇵​​🇮​​🇳​​🇹​​🇪​​🇷​​🇪​​🇸​​🇹​ ​🇱​​🇮​​🇳​​🇰​.')
                return
            
            await processing_msg.edit_text("⏳ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ᴘɪɴᴛᴇʀᴇꜱᴛ ᴍᴇᴅɪᴀ...")
            
            # Prepare file path
            file_path = Config.TEMP_DIR / f"temp_{message.chat.id}_{pin_id}"
            file_path = file_path.with_suffix('.mp4' if media_data.media_type == 'video' else '.jpg')
            
            # Asynchronous download
            async def download_file(url, file_path):
                async with self.downloader.session.get(url) as response:
                    if response.status == 200:
                        with open(file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        return True
                return False
            
            # Download media
            download_success = await download_file(media_data.url, file_path)
            
            if download_success and os.path.getsize(file_path):
            # Create progress tracker
                file_size_bytes = os.path.getsize(file_path)
                progress_tracker = UploadProgressTracker(processing_msg, file_size_bytes)
                
                # Send media using Pyrogram with progress tracking
                try:
                    if media_data.media_type == "video":
                        await client.send_video(
                            chat_id=message.chat.id,
                            video=file_path,
                            supports_streaming=True,
                            progress=progress_tracker.progress_callback
                        )
                    else:
                        await client.send_photo(
                            chat_id=message.chat.id,
                            photo=file_path,
                            progress=progress_tracker.progress_callback
                        )
                    
                    # Delete processing message
                    await processing_msg.delete()
                    
                except Exception as e:
                    logger.error(f"Send media error: {e}")
                    await processing_msg.edit_text('​🇫​​🇦​​🇮​​🇱​​🇪​​🇩​ ​🇹​​🇴​ ​🇸​​🇪​​🇳​​🇩​ ​🇲​​🇪​​🇩​​🇮​​🇦​. ​🇵​​🇱​​🇪​​🇦​​🇸​​🇪​ ​🇹​​🇷​​🇾​ ​🇦​​🇬​​🇦​​🇮​​🇳​ ​🇱​​🇦​​🇹​​🇪​​🇷​.')
                
                # Cleanup
                if os.path.exists(file_path):
                    os.remove(file_path)
            
        except Exception as e:
            logger.error(f"Error processing Pinterest message: {e}")
            await processing_msg.edit_text('ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ʀᴇQᴜᴇꜱᴛ.')

    def run(self):
        """Start the bot"""
        logger.info("Starting Pyrogram bot...")
        self.app.run()

def main():
    bot = PinterestFacebookBot()
    bot.run()

if __name__ == '__main__':
    main()
