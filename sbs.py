import threading
import time
import json
import re
import requests
from datetime import datetime, timedelta

# Global variables to store click count, max clicks, and a stop event
click_count = 0
max_clicks = 0
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

# Function to perform the HTTP request and extract click count
def http_request(url):
    global click_count
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
                click_count = int(json_data["Response_Data_For_Detail"].get("CLICK_CNT", 0))
                if click_count >= max_clicks:
                    if not stop_event.is_set():
                        stop_event.set()
                        print(f"Click count reached {click_count}, stopping script.")
        except (requests.RequestException, json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"Error during request or parsing JSON: {e}")
        
        time.sleep(1)

# Function to print the aggregated click count 1 second after the minute mark
def print_click_count():
    while not stop_event.is_set():
        now = datetime.now()
        next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1))
        sleep_duration = (next_minute - now).total_seconds() + 1
        time.sleep(sleep_duration)

        with lock:
            print(f'Total Click Count: {click_count}')
            if click_count >= max_clicks:
                stop_event.set()
                return

# Load configuration from JSON file
with open('config.json', 'r') as config_file:
    config = json.load(config_file)
    user_url = config['url']
    threads_count = config['threads']
    max_clicks = config.get('max_clicks', 0)

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

# Print initial message to indicate the script is running
print(f"Starting script for '{title}'")

# Start the specified number of threads
threads = []
for _ in range(threads_count):
    thread = threading.Thread(target=http_request, args=(api_url,))
    thread.daemon = True  # This allows the threads to exit when the main program exits
    thread.start()
    threads.append(thread)

# Print the initial click count
time.sleep(2)
print(f'Initial Click Count: {click_count}')

# Start a thread to print the click count 1 second after the minute mark
print_thread = threading.Thread(target=print_click_count)
print_thread.daemon = True
print_thread.start()

# Keep the main thread alive to allow threads to run
try:
    while not stop_event.is_set():
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping script.")
