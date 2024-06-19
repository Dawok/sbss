import threading
import time
import json
import re
import requests
from datetime import datetime
import pytz

# Global variables to store page views, max page views, and a stop event
page_views = 0
max_page_views = 0
initial_update_done = False
lock = threading.Lock()
stop_event = threading.Event()

# Function to construct the API URL from the provided URL
def construct_api_url(url):
    match = re.search(r'board_no=(\d+)', url)
    if match:
        board_no = match.group(1)
        api_url = f"https://api.board.sbs.co.kr/bbs/V2.0/basic/board/detail/{board_no}?callback=boardViewCallback_inkigayo_pt01&action_type=callback&board_code=inkigayo_pt01&jwt-token=&_={int(time.time() * 1000)}"
        return api_url
    else:
        raise ValueError("Invalid URL format. Could not find 'board_no' parameter.")

# Function to perform the HTTP request and extract page views
def http_request(url):
    global page_views, initial_update_done
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.53 Safari/537.36'
    }
    while not stop_event.is_set():
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            jsonp_data = response.text
            json_data = json.loads(re.search(r'\((.*)\)', jsonp_data).group(1))  # Remove JSONP wrapping
            with lock:
                new_page_views = int(json_data["Response_Data_For_Detail"].get("CLICK_CNT", 0))
                if new_page_views != page_views or not initial_update_done:
                    page_views = new_page_views
                    current_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')
                    if not initial_update_done:
                        print(f"[{current_time}] Starting script for '{title}'")
                        initial_update_done = True
                    print(f'[{current_time}] Page Views: {page_views}')
                    if page_views >= max_page_views:
                        if not stop_event.is_set():
                            stop_event.set()
                            print(f"[{current_time}] Page views reached {page_views}, stopping script.")
        except (requests.RequestException, json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"Error during request or parsing JSON: {e}")
        
        time.sleep(1)

# Load configuration from JSON file
with open('config.json', 'r') as config_file:
    config = json.load(config_file)
    user_url = config['url']
    threads_count = config['threads']
    max_page_views = config.get('max_page_views', 0)
    timezone = config.get('timezone', 'UTC')

# Set timezone
if timezone:
    try:
        tz = pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
        print(f"Unknown timezone: {timezone}. Using system local time instead.")
        tz = None
else:
    tz = None

# Use local timezone if no timezone is specified or an error occurs
if tz is None:
    tz = datetime.now().astimezone().tzinfo

# Construct the API URL from the provided URL
api_url = construct_api_url(user_url)

# Get the title from the initial HTTP request
try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.53 Safari/537.36'
    }
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    jsonp_data = response.text
    json_data = json.loads(re.search(r'\((.*)\)', jsonp_data).group(1))  # Remove JSONP wrapping
    title = json_data["Response_Data_For_Detail"].get("TITLE", "Unknown Title")
except (requests.RequestException, json.JSONDecodeError, ValueError, TypeError) as e:
    print(f"Error during initial request or parsing JSON for title: {e}")
    title = "Unknown Title"

# Start the initial message to indicate the script is running
current_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')

# Start the specified number of threads
threads = []
for _ in range(threads_count):
    thread = threading.Thread(target=http_request, args=(api_url,))
    thread.daemon = True  # This allows the threads to exit when the main program exits
    thread.start()
    threads.append(thread)

# Keep the main thread alive to allow threads to run
try:
    while not stop_event.is_set():
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping script.")
