# SBSS Small brain syndrome script
This script monitors page views from a SBS Inkigayo board URL. It can be configured to stop automatically when the maximum page view threshold is reached.

## Prerequisites

- Python 3.x
- Required Python packages: `requests`, `pytz`

Install the required packages using pip:
```bash
pip install requests pytz
```

## Configuration

The script uses a configuration file (`config.json`) for its settings:

```json
{
    "url": "",
    "threads": 5,
    "max_page_views": 1000000,
    "timezone": "Asia/Seoul"
}
```

- **url**: The URL of the webpage whose page views are monitored. The script automatically constructs the API URL from this.
- **threads**: Number of threads to run concurrently for monitoring.
- **max_page_views**: The script stops automatically when the page views reach or exceed this number.
- **timezone**: Timezone used for displaying timestamps in the output. Uses the system local time if not specified or if an invalid timezone is provided.

## How to Run

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Dawok/sbss
   cd sbss
   ```

2. **Configure `config.json`**:
   - Modify `config.json` to specify the URL, number of threads, maximum page views, and timezone.

3. **Run the script**:
   Execute the Python script `sbs.py`:
   ```bash
   python sbs.py
   ```
