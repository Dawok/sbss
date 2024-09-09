import threading
import time
import json
import re
import requests
from datetime import datetime
import socket

page_views = 0
max_page_views = 0
initial_update_done = False
lock = threading.Lock()
stop_event = threading.Event()
error_sent = False
hostname = socket.gethostname()
total_requests = 0

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
    global page_views, initial_update_done, error_sent, total_requests
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
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    total_requests += 1
                    if not initial_update_done:
                        initial_update_done = True
                        send_start_discord_webhook(page_views, max_page_views, threads_count, current_time)
                    print(f'[{current_time}] Page Views: {page_views}')
                    if page_views >= max_page_views:
                        if not stop_event.is_set():
                            stop_event.set()
                            print(f"[{current_time}] Page views reached {page_views}, stopping script.")
                            send_threshold_discord_webhook(page_views, max_page_views, current_time)
        except (requests.RequestException, json.JSONDecodeError, ValueError, TypeError) as e:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{current_time}] Error during request or parsing JSON: {e}")
            if not error_sent:
                send_error_discord_webhook(str(e), current_time)
                error_sent = True
        
        time.sleep(1)
	    
# Function to send Discord webhook with embed for script start
def send_start_discord_webhook(current_views, target_views, thread_count, current_time):
    webhook_url = config.get('discord_webhook')
    url = config.get('url')
    if webhook_url:
        embed = {
            "embeds": [{
                "title": f"Script Started for '{title}' on {hostname}",
                "description": f"Current Page Views: {current_views}\nTarget Page Views: {target_views}\nThread Count: {thread_count}",
                "color": 3447003,
		"url": url,
                "footer": {
                    "text": f"Script started at {current_time}"
                }
            }]
        }
        headers = {
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(webhook_url, json=embed, headers=headers)
            response.raise_for_status()
            print(f"[{current_time}] Discord webhook sent successfully for script start.")
        except requests.RequestException as e:
            print(f"Error sending Discord webhook for script start: {e}")

# Function to send Discord webhook with embed for threshold reached
def send_threshold_discord_webhook(current_views, target_views, current_time):
    webhook_url = config.get('discord_webhook')
    url = config.get('url')
    if webhook_url:
        embed = {
            "embeds": [{
                "title": f"Page Views Reached on {hostname}!",
                "description": f"The page views reached {current_views}. Stopping script.",
                "color": 6029150,
                "url": url,
                "footer": {
                    "text": f"Threshold reached at {current_time}"
                }
            }]
        }
        headers = {
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(webhook_url, json=embed, headers=headers)
            response.raise_for_status()
            print(f"[{current_time}] Discord webhook sent successfully for threshold reached.")
        except requests.RequestException as e:
            print(f"Error sending Discord webhook for threshold reached: {e}")

# Function to send Discord webhook with embed for HTTP error
def send_error_discord_webhook(error_message, current_time):
    webhook_url = config.get('discord_webhook')
    if webhook_url:
        embed = {
            "embeds": [{
                "title": f"HTTP Error Encountered on {hostname}",
                "description": f"An error occurred: {error_message}",
                "color": 15158332,
                "footer": {
                    "text": f"Error encountered at {current_time}"
                }
            }]
        }
        headers = {
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(webhook_url, json=embed, headers=headers)
            response.raise_for_status()
            print(f"[{current_time}] Discord webhook sent successfully for HTTP error.")
        except requests.RequestException as e:
            print(f"Error sending Discord webhook for HTTP error: {e}")

# Load configuration from JSON file
with open('config.json', 'r') as config_file:
    config = json.load(config_file)
    user_url = config['url']
    threads_count = config['threads']
    max_page_views = config.get('max_page_views', 0)

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
current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
finally:
    # When the script ends, print the total accepted requests
    print(f"Total accepted requests: {total_requests}")
