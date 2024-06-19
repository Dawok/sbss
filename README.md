# SBS click monitor script

A Python script that monitors the click count of a sbs board and helps a bit with the clicks depending on thread count.

## Features

- Configurable URL and number of threads.
- Automatically converts a given URL to the corresponding API URL.
- Handles JSONP responses and extracts the click count.
- Prints the click count every minute.
- Uses Python's `requests` library for HTTP requests.

## Requirements

- Python 3.x
- `requests` library

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/Dawok/sbss.git
    cd sbss
    ```

2. Install the required library:
    ```bash
    pip install requests
    ```

## Configuration

Edit the `config.json` file in the root directory of the project with the following structure:

```json
{
    "url": "BOARD_URL",
    "threads": 5
}
