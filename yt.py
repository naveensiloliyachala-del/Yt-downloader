import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp import YoutubeDL
import os
import requests
import json
import logging
import urllib.parse
import threading
import time
from dotenv import load_dotenv
from database import connect_db, ensure_user_in_db, create_user_downloads_table, get_download_count, increment_download_count, reset_database
from requests.exceptions import ConnectionError, SSLError
import re
from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime

# Set up basic logging
logging.basicConfig(level=logging.DEBUG)

# List of user IDs that can bypass verification
admin_user_ids = [8389778575, 7068000043]  # Replace with actual user IDs

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("8811766132:AAE15uyY5G30kWbsDHE893VVglVCX2IkRIs")
TELEGRAM_UPLOAD_LIMIT = 50 * 1024 * 1024  # 50 MB
DOWNLOAD_PATH = "/app/downloads/"
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# Initialize the bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Path to your cookies file in Railway project
COOKIES_PATH = "/app/cookies.txt"

# Initialize Flask
app = Flask(__name__)

def delete_file_after_delay(file_path, chat_id):
    time.sleep(1800)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.debug(f"Deleted file: {file_path}")
            bot.send_message(chat_id, f"The file {os.path.basename(file_path)} has been deleted from the server after 30 minutes.")
        else:
            logging.error(f"File not found: {file_path} - could not delete")
    except Exception as e:
        logging.error(f"Error deleting file: {file_path}, Error: {e}")

def shorten_url(long_url):
    api_token = os.getenv('ADTIVAL_API_TOKEN')
    api_url = f"https://www.adtival.network/api?api={api_token}&url={long_url}&format=json"
    
    response = requests.get(api_url)
    if response.status_code == 200:
        try:
            result = response.json()
            if result['status'] == 'success':
                return result['shortenedUrl']
            else:
                logging.error(f"Error from Adtival: {result['message']}")
                return long_url  # Fallback to the original URL if there's an error
        except json.JSONDecodeError:
            logging.error("Error decoding JSON response from Adtival")
            return long_url  # Fallback to the original URL if there's an error
    else:
        logging.error(f"Error shortening URL: {response.status_code}")
        return long_url  # Fallback to the original URL if there's an error

def get_verification_url(filepath):
    adtival_api_url = "https://www.adtival.network/api"
    api_key = os.getenv('ADTIVAL_API_TOKEN')  # Ensure your API token is correctly set in the environment variables
    params = {
        'api': api_key,
        'url': f"https://web-production-f9ab3.up.railway.app/downloads/{filepath}",  # Use your actual domain
        'format': 'json'
    }
    response = requests.get(adtival_api_url, params=params)
    data = response.json()
    
    if 'shortenedUrl' in data:
        return data['shortenedUrl']
    else:
        logging.error("Failed to generate shortened URL")
        return None

# Test the URL shortening function
short_url = shorten_url("https://web-production-f9ab3.up.railway.app/downloads/samplefile.mp4")
print("Shortened URL:", short_url)

def get_unique_filepath(base_filepath, ext):
    counter = 1
    filepath = f"{base_filepath}{ext}"
    while os.path.exists(filepath):
        filepath = f"{base_filepath}_{counter}{ext}"
        counter += 1
    return filepath

def send_video_with_retries(file_path, chat_id, retries=3):
    for attempt in range(retries):
        try:
            with open(file_path, 'rb') as video:
                bot.send_video(chat_id, video)
            return True
        except Exception as e:
            logging.error(f"Error uploading video, attempt {attempt + 1}/{retries}: {e}")
            time.sleep(5)
    return False

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "_", filename)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_message = (
        "👋 Welcome to the Video Downloader Bot! 🎉\n\n"
        "📹 **What I Can Do**:\n"
        "Send me any YouTube, Dailymotion, or TikTok link, and I'll help you download the video. If the video file is too large for Telegram, I'll provide you with a convenient download link.\n\n"
        "📅 **Daily Limit**:\n"
        "You can download up to **2 videos per day**. If you reach your limit, you'll need to verify to continue downloading. Some users can download without limits based on their verification status.\n\n"
        "🔍 **Quality Options**:\n"
        "Higher quality downloads, such as 4K and 2K, require verification. Enjoy your videos in the best possible quality after verifying your account!\n\n"
        "🛠️ **Beta Notice**:\n"
        "This bot is currently in beta. If you encounter any problems or bugs, please report them to @Amanadmin69.\n\n"
        "🚀 **Get Started**:\n"
        "Just send me a video link to get started. Enjoy! 🎥"
    )
    
    bot.send_message(message.chat.id, welcome_message)

# Telegram Bot Command for Resetting Database
@bot.message_handler(commands=['reset'])
def reset_database_command(message):
    user_id = message.chat.id
    if user_id in admin_user_ids:
        if reset_database():
            bot.send_message(user_id, "Database has been reset successfully.")
        else:
            bot.send_message(user_id, "Failed to reset the database. Please try again later.")
    else:
        bot.send_message(user_id, "You don't have the required permissions to reset the database.")

# Flask Route for Downloading Files
@app.route('/downloads/<path:filename>')
def download_file(filename):
    try:
        decoded_filename = urllib.parse.unquote(filename)
        full_path = os.path.join(DOWNLOAD_PATH, decoded_filename)
        print(f"Looking for file at: {full_path}")  # Debug statement
        return send_from_directory(DOWNLOAD_PATH, decoded_filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

# Flask Route for Resetting Database
@app.route('/reset', methods=['POST'])
def reset_database_route():
    try:
        if reset_database():
            return jsonify({"status": "success", "message": "Database has been reset successfully."}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to reset the database."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bot.message_handler(func=lambda message: True)
def handle_link(message):
    url = message.text
    logging.debug(f"Received URL: {url}")
    bot.reply_to(message, "Fetching available video qualities, please wait...")

    if 'youtube.com' in url or 'youtu.be' in url:
        handle_youtube_video(url, message)
    elif 'dailymotion.com' in url or 'dai.ly' in url:
        handle_dailymotion_video(url, message)
    elif 'tiktok.com' in url:
        handle_tiktok_video(url, message)
    else:
        bot.reply_to(message, "Please send a valid YouTube, Dailymotion, or TikTok link.")

def handle_youtube_video(url, message):
    try:
        ydl_opts = {
            'noplaylist': True,
            'cookies': COOKIES_PATH  # Add the path to your cookies file
        }

        if 'youtube.com' in url:
            url_parts = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(url_parts.query)
            video_id = query_params['v'][0]
        elif 'youtu.be' in url:
            video_id = url.split('/')[-1]
        else:
            bot.reply_to(message, "Invalid YouTube link format.")
            return

        clean_url = f"https://www.youtube.com/watch?v={video_id}"

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            formats = info.get('formats', [])
            keyboard = InlineKeyboardMarkup()
            quality_set = set()
            for f in formats:
                if f['vcodec'] != 'none':
                    quality = str(f.get('format_note'))
                    format_id = f['format_id']
                    if quality and quality.lower() != 'none' and quality.strip():
                        if quality not in quality_set:
                            quality_set.add(quality)
                            callback_data = f'{format_id}|{video_id}|{quality}|youtube'
                            keyboard.add(InlineKeyboardButton(text=quality, callback_data=callback_data))
            callback_data = f'mp3|{video_id}|mp3|youtube'
            keyboard.add(InlineKeyboardButton(text="MP3", callback_data=callback_data))

            if quality_set:
                bot.reply_to(message, "Choose the video quality:", reply_markup=keyboard)
            else:
                bot.reply_to(message, "No video qualities available for this link.")
    except Exception as e:
        logging.error(f"Error fetching video qualities: {e}")
        bot.reply_to(message, f"Failed to fetch video qualities. Error: {e}")

admin_user_ids = [8389778575, 7068000043]  # Replace with actual user IDs

def get_download_link(file_name, resolution, user_id):
    conn = connect_db()
    logging.info(f"Entered get_download_link for user {user_id}, resolution {resolution}")
    ensure_user_in_db(conn, user_id)  # Ensure user exists in the database

    if user_id in admin_user_ids:
        logging.info(f"User {user_id} is an admin, bypassing Adtival")
        encoded_file_name = urllib.parse.quote(file_name)
        download_link = f"https://web-production-f9ab3.up.railway.app/downloads/{encoded_file_name}"
    else:
        download_count = get_download_count(conn, user_id)
        logging.info(f"User {user_id} has download count {download_count}")

        if resolution in ["1440p", "2160p"]:
            logging.info("Resolution is 1440p or 2160p, using Adtival")
            encoded_file_name = urllib.parse.quote(file_name)
            long_url = f"https://web-production-f9ab3.up.railway.app/downloads/{encoded_file_name}"
            download_link = shorten_url(long_url)
        elif resolution == "1080p" and download_count == 0:
            logging.info("First 1080p download, not using Adtival")
            encoded_file_name = urllib.parse.quote(file_name)
            download_link = f"https://web-production-f9ab3.up.railway.app/downloads/{encoded_file_name}"
        elif resolution == "1080p":
            logging.info("Subsequent 1080p download, using Adtival")
            encoded_file_name = urllib.parse.quote(file_name)
            long_url = f"https://web-production-f9ab3.up.railway.app/downloads/{encoded_file_name}"
            download_link = shorten_url(long_url)
        else:
            if download_count < 2:
                logging.info("First two downloads for other resolutions, not using Adtival")
                encoded_file_name = urllib.parse.quote(file_name)
                download_link = f"https://web-production-f9ab3.up.railway.app/downloads/{encoded_file_name}"
            else:
                logging.info("Subsequent downloads for other resolutions, using Adtival")
                encoded_file_name = urllib.parse.quote(file_name)
                long_url = f"https://web-production-f9ab3.up.railway.app/downloads/{encoded_file_name}"
                download_link = shorten_url(long_url)

        increment_download_count(conn, user_id)
    conn.close()
    logging.info(f"Generated download link: {download_link}")
    return download_link

@bot.message_handler(commands=['download'])
def handle_download_command(message):
    user_id = message.chat.id
    video_url = message.text.split(' ')[1]  # Assuming the format is /download <video_url>
    resolution = "1080p"  # Set resolution based on user input or default to 1080p

    conn = connect_db()
    ensure_user_in_db(conn, user_id)  # Ensure user exists in the database
    
    # Download the video and get the actual file name using yt-dlp
    ydl_opts = {
        'format': f'bestvideo[height<={resolution}]+bestaudio/best',
        'outtmpl': f'{DOWNLOAD_PATH}%(title)s.%(ext)s',
    }
    with YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(video_url, download=True)
        file_name = ydl.prepare_filename(info_dict)
        file_name = os.path.basename(file_name)  # Get the actual file name

    download_link = get_download_link(file_name, resolution, user_id)

    bot.send_message(user_id, f"Here is your download link: {download_link}")
    conn.close()  # Close the database connection

def send_download_button(chat_id, file_name, resolution, user_id):
    original_download_link = get_download_link(file_name, resolution, user_id)
    logging.info(f"Generated download link: {original_download_link}")

    keyboard = InlineKeyboardMarkup()
    download_button = InlineKeyboardButton(text="Download", url=original_download_link)
    keyboard.add(download_button)

    bot.send_message(chat_id, (
        "The file is too large to upload to Telegram because the Telegram bot has a 50 MB upload limit. "
        "You can download it using the button below.\n\n"
        "Please download the file within 30 minutes. The file will be deleted from the server after 30 minutes to keep the server clean and efficient."
    ), reply_markup=keyboard)

def handle_dailymotion_video(url, message):
    try:
        ydl_opts = {'quiet': True, 'noplaylist': True, 'force_generic_extractor': True}

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            keyboard = InlineKeyboardMarkup()
            quality_set = set()

            for f in formats:
                if f['vcodec'] != 'none':
                    quality = str(f.get('format_note') or f.get('resolution'))
                    format_id = f['format_id']
                    if quality not in quality_set:
                        quality_set.add(quality)
                        callback_data = f'{format_id}|{info["id"]}|{quality}|dailymotion'
                        keyboard.add(InlineKeyboardButton(text=quality, callback_data=callback_data))
            # Add MP3 option
            callback_data = f'mp3|{info["id"]}|mp3|dailymotion'
            keyboard.add(InlineKeyboardButton(text="MP3", callback_data=callback_data))

            if quality_set:
                bot.reply_to(message, "Choose the video quality:", reply_markup=keyboard)
            else:
                bot.reply_to(message, "No video qualities available for this link.")
    except Exception as e:
        logging.error(f"Error fetching video qualities: {e}")
        bot.reply_to(message, f"Failed to fetch video qualities. Error: {e}")

def check_tiktok_accessibility():
    try:
        response = requests.get("https://www.tiktok.com")
        if response.status_code == 200:
            print("TikTok is accessible")
        else:
            print("TikTok is not accessible")
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")

def handle_tiktok_video(url, message):
    chat_id = message.chat.id
    try:
        logging.debug(f"Starting to download TikTok video: {url}")

        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{DOWNLOAD_PATH}%(title)s.%(ext)s',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'max-age=0',
                'Connection': 'keep-alive',
                'Pragma': 'no-cache',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://www.tiktok.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            },
            'verbose': True,
            'logger': logging.getLogger()
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            logging.debug(f"Video info: {info}")

            file_path = ydl.prepare_filename(info)
            logging.debug(f"File path: {file_path}")

            base_filepath, ext = os.path.splitext(file_path)
            unique_filepath = get_unique_filepath(base_filepath, ext)

            if os.path.exists(file_path):
                os.rename(file_path, unique_filepath)
                logging.debug(f"File renamed to: {unique_filepath}")

            file_name = os.path.basename(unique_filepath)

            if os.path.exists(unique_filepath):
                file_size = os.path.getsize(unique_filepath)
                logging.debug(f"Downloaded file size: {file_size}")

                if file_size <= TELEGRAM_UPLOAD_LIMIT:
                    if send_video_with_retries(unique_filepath, chat_id):
                        os.remove(unique_filepath)
                        logging.debug(f"Deleted file after upload: {unique_filepath}")
                    else:
                        logging.error("Failed to upload video after multiple attempts")
                        bot.send_message(chat_id, "Failed to upload video after multiple attempts.")
                else:
                    send_download_button(chat_id, file_name)
                    threading.Thread(target=delete_file_after_delay, args=(unique_filepath, chat_id)).start()
            else:
                logging.error(f"File not found: {unique_filepath}")
                bot.send_message(chat_id, "Failed to download video. File not found after download.")
    except Exception as e:
        logging.error(f"Error during video processing: {e}", exc_info=True)
        bot.send_message(chat_id, "Failed to download video. Currently, TikTok downloads are unavailable due to regional restrictions. Our servers are located in the US, where TikTok has imposed stricter access controls. This means we're currently unable to download TikTok videos. We apologize for the inconvenience and appreciate your understanding.")

@bot.callback_query_handler(func=lambda call: True)
def handle_quality_callback(call):
    logging.debug(f"Quality callback data: {call.data}")
    try:
        data = call.data.split('|')
        logging.debug(f"Parsed callback data: {data}")

        if len(data) < 4:
            raise ValueError("Incomplete callback data received.")

        format_id, video_id, quality, source = data

        if source == 'dailymotion':
            url = f"https://www.dailymotion.com/video/{video_id}"
        elif source == 'youtube':
            url = f"https://www.youtube.com/watch?v={video_id}"
        else:
            url = f"https://www.tiktok.com/@{video_id}"

        logging.debug(f"Downloading video from URL: {url}")

        if quality == "mp3":
            bot.send_message(call.message.chat.id, "Converting audio to MP3, please wait...")

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_PATH, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'noplaylist': True,
                'cookies': COOKIES_PATH  # Add the path to your cookies file
            }

            with YoutubeDL(ydl_opts) as ydl:
                logging.debug("Downloading and converting audio")
                info = ydl.extract_info(url, download=True)
                logging.debug(f"Downloaded info: {info}")
                file_path = ydl.prepare_filename(info)
                logging.debug(f"Prepared file path: {file_path}")

                # Ensure the MP3 file path is correct
                base_filepath, ext = os.path.splitext(file_path)
                mp3_filepath = base_filepath + ".mp3"
                logging.debug(f"MP3 file path: {mp3_filepath}")

                # Check if the MP3 file exists
                if os.path.exists(mp3_filepath):
                    file_name = os.path.basename(mp3_filepath)
                    file_size = os.path.getsize(mp3_filepath)
                    logging.debug(f"MP3 file size: {file_size}")

                    process_audio(mp3_filepath, file_size, file_name, call)
                else:
                    logging.error(f"File not found: {mp3_filepath}")
                    bot.send_message(call.message.chat.id, "Failed to download audio. File not found after download.")
        else:
            bot.send_message(call.message.chat.id, f"Downloading video in {quality}, please wait...")

            ydl_opts = {
                'format': f'{format_id}+bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_PATH, '%(title)s_%(format_id)s.%(ext)s'),
                'noplaylist': True,
                'merge_output_format': 'mp4',
                'cookies': COOKIES_PATH  # Add the path to your cookies file
            }

            with YoutubeDL(ydl_opts) as ydl:
                logging.debug(f"Starting video download with options: {ydl_opts}")
                info = ydl.extract_info(url, download=True)
                logging.debug(f"Downloaded video info: {info}")
                file_path = ydl.prepare_filename(info)
                logging.debug(f"Prepared file path: {file_path}")
                base_filepath, ext = os.path.splitext(file_path)
                logging.debug(f"Base file path: {base_filepath}, Extension: {ext}")
                unique_filepath = get_unique_filepath(base_filepath, ext)
                logging.debug(f"Unique file path: {unique_filepath}")

                if os.path.exists(file_path):
                    os.rename(file_path, unique_filepath)
                    logging.debug(f"Renamed file to unique path: {unique_filepath}")

                file_name = os.path.basename(unique_filepath)

                if os.path.exists(unique_filepath):
                    file_size = os.path.getsize(unique_filepath)
                    logging.debug(f"Downloaded file size: {file_size}")

                    process_file(unique_filepath, file_size, file_name, call)
                else:
                    logging.error(f"File not found after download: {unique_filepath}")
                    bot.send_message(call.message.chat.id, "Failed to download video. File not found after download.")
    except ValueError as ve:
        logging.error(f"ValueError: {ve}")
        bot.send_message(call.message.chat.id, f"Error processing video quality: {ve}")
    except Exception as e:
        logging.error(f"Error during video processing: {e}")
        bot.send_message(call.message.chat.id, f"Failed to download video. Error: {e}")

def process_audio(unique_filepath, file_size, file_name, call):
    if os.path.exists(unique_filepath):
        logging.debug(f"File exists: {unique_filepath}")
        
        if file_size <= TELEGRAM_UPLOAD_LIMIT:
            if send_audio_with_retries(unique_filepath, call.message.chat.id):
                if os.path.exists(unique_filepath):
                    os.remove(unique_filepath)
                    logging.debug(f"Deleted file after upload: {unique_filepath}")
            else:
                logging.error("Failed to upload audio after multiple attempts")
                bot.send_message(call.message.chat.id, "Failed to upload audio after multiple attempts.")
        else:
            original_download_link = get_download_link(file_name)
            short_download_link = shorten_url(original_download_link)
            bot.send_message(call.message.chat.id, (
                "The file is too large to upload to Telegram because the Telegram bot has a 50 MB upload limit. "
                "You can download it using the link below.\n\n"
                f"{short_download_link}\n\n"
                "Please download the file within 30 minutes. The file will be deleted from the server after 30 minutes to keep the server clean and efficient."
            ))
            threading.Thread(target=delete_file_after_delay, args=(unique_filepath, call.message.chat.id)).start()
    else:
        logging.error(f"File not found: {unique_filepath}")
        bot.send_message(call.message.chat.id, "Failed to find the MP3 file after conversion.")

def send_audio_with_retries(file_path, chat_id, retries=3):
    for attempt in range(retries):
        try:
            bot.send_audio(chat_id, audio=open(file_path, 'rb'))
            logging.debug(f"Successfully sent audio: {file_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to send audio (Attempt {attempt + 1}): {e}")
            if attempt < retries - 1:
                time.sleep(2)  # Wait before retrying
    return False

def sanitize_and_encode_filename(filename):
    sanitized_filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    encoded_filename = urllib.parse.quote(sanitized_filename)
    return encoded_filename

def setup_database():
    conn = connect_db()
    create_user_downloads_table(conn)

# Call this function at the start of your script
setup_database()

def process_file(unique_filepath, file_size, file_name, call):
    user_id = call.message.chat.id
    conn = connect_db()  # Ensure you establish a database connection
    resolution = "1080p"  # Set the appropriate resolution

    # Check if user is an admin or mod
    if user_id in admin_user_ids:
        bypass_verification = True
    else:
        bypass_verification = False

    if bypass_verification or get_download_count(conn, user_id) < 2:
        # Allow download without verification
        file_name = sanitize_and_encode_filename(file_name)
        if file_size <= TELEGRAM_UPLOAD_LIMIT:
            if send_video_with_retries(unique_filepath, call.message.chat.id):
                os.remove(unique_filepath)
                logging.debug(f"Deleted file after upload: {unique_filepath}")
                increment_download_count(conn, user_id)
            else:
                logging.error("Failed to upload video after multiple attempts")
                bot.send_message(call.message.chat.id, "Failed to upload video after multiple attempts.")
        else:
            send_download_button(call.message.chat.id, file_name, resolution, user_id)
            threading.Thread(target=delete_file_after_delay, args=(unique_filepath, call.message.chat.id)).start()
    else:
        # Require verification after two downloads
        verification_url = get_verification_url(file_name)  # Use sanitized filename
        if verification_url:
            keyboard = InlineKeyboardMarkup()
            download_button = InlineKeyboardButton(text="Verify and Download", url=verification_url)
            keyboard.add(download_button)
            bot.send_message(user_id, (
                "You have reached your download limit of 2 per day. Please use the verification link for further downloads."
            ), reply_markup=keyboard)
        else:
            bot.send_message(user_id, "Failed to generate verification link. Please try again later.")

def send_video_with_retries(file_path, chat_id, retries=3):
    for attempt in range(retries):
        try:
            with open(file_path, 'rb') as video:
                bot.send_video(chat_id, video)
            return True
        except Exception as e:
            logging.error(f"Error uploading video, attempt {attempt + 1}/{retries}: {e}")
            time.sleep(5)
    return False

def start_polling():
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except requests.exceptions.ReadTimeout as e:
            logging.error(f"ReadTimeoutError: {e}, retrying in 15 seconds...")
            time.sleep(15)
        except Exception as e:
            logging.error(f"Exception occurred: {e}, retrying in 15 seconds...")
            time.sleep(15)

# Start polling for the bot in a thread with retry mechanism
threading.Thread(target=start_polling).start()

# Flask routes
@app.route('/')
def hello():
    return "Hello, World!"

@app.route('/test')
def test():
    return "Test route working!"

@app.route('/download', methods=['GET'])
def download():
    url = request.args.get('url')
    quality = request.args.get('quality', 'best')
    source = request.args.get('source', 'youtube')

    if not url:
        return jsonify({"error": "URL parameter is missing"}), 400

    logging.debug(f"Received download request: url={url}, quality={quality}, source={source}")

    try:
        file_path, file_name = download_video(url, quality, source)
        if file_path:
            return jsonify({"status": "success", "file_path": file_path, "file_name": file_name}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to download video"}), 500
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Flask helper functions
def download_video(url, quality, source):
    try:
        ydl_opts = {
            'format': quality,
            'outtmpl': os.path.join(DOWNLOAD_PATH, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'cookies': COOKIES_PATH  # Ensure the path to the cookies file is correct
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            base_filepath, ext = os.path.splitext(file_path)
            unique_filepath = get_unique_filepath(base_filepath, ext)

            if os.path.exists(file_path):
                os.rename(file_path, unique_filepath)
                logging.debug(f"Renamed file to unique path: {unique_filepath}")
            else:
                logging.error(f"File not found after download: {file_path}")
                return None, None

            file_name = os.path.basename(unique_filepath)
            file_size = os.path.getsize(unique_filepath)
            logging.debug(f"Downloaded file size: {file_size}")

            threading.Thread(target=delete_file_after_delay, args=(unique_filepath,)).start()
            return unique_filepath, file_name
    except Exception as e:
        logging.error(f"Error during video download: {e}")
        return None, None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
