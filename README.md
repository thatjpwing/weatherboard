# NOAA / NWS Terminal Weather Dashboard (`weatherboard`)

A real-time, interactive terminal weather dashboard powered by official **NOAA / National Weather Service (NWS)** and **Aviation Weather Center** APIs. Built with Python and `rich`, it displays live local observations, extended forecasts, active severe weather alerts, and one-key browser shortcuts for radar and Storm Prediction Center (SPC) resources.

## Features

* **Flexible Location Lookup:** Query weather by **ICAO airport/station code** (e.g., `KJFK`, `KTUS`, `KPHL`, `KLAX`) or **5-digit US ZIP code** (e.g., `10001`, `85701`).

* **Live Local Observations:** Displays temperature (°F), sky condition, wind speed, relative humidity, barometric pressure (mb), and visibility (mi).

* **Extended Forecast:** Shows the next 8 NWS forecast periods with temperatures, wind speed/direction, and short summaries.

* **Active Alerts & Warnings:** Automatically checks your local NWS forecast zone for active watches, warnings, and advisories, highlighting severe/extreme events.

* **Interactive Browser Quick Links:** Launch official NWS forecast pages, live NEXRAD radar, the Storm Prediction Center (SPC), Area Forecast Discussions (AFD), or active alert details directly in your default web browser with a single keypress.

* **Auto-Refresh & Cross-Platform Controls:** Runs in a clean full-screen terminal UI with configurable auto-refresh intervals and non-blocking keyboard shortcuts on macOS, Linux, and Windows.

## Requirements

* **Python 3.9+**

* Third-party packages:

  * `requests`

  * `rich`

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/thatjpwing/weatherboard.git
   cd weatherboard
   ```

2. **Install dependencies:**

   ```bash
   pip install requests rich
   ```

3. *(Optional)* **Make the script executable** on macOS/Linux:

   ```bash
   chmod +x weatherboard.py
   ```

## Usage

Run the script using Python (defaults to John F. Kennedy International Airport, `KJFK`, refreshing every 600 seconds):

```bash
python3 weatherboard.py
```

### Specify a Station or ZIP Code

Use `-s` or `--station` with an ICAO code or 5-digit US ZIP code:

```bash
# By ICAO airport/station code
python3 weatherboard.py -s KPHL

# By 5-digit US ZIP code
python3 weatherboard.py -s 10001
```

### Custom Refresh Interval

Use `--refresh` to set the automatic update interval in seconds:

```bash
# Refresh every 5 minutes (300 seconds)
python3 weatherboard.py -s KDEN --refresh 300
```

### Command-Line Options

| Flag | Description | Default | 
| ----- | ----- | ----- | 
| `-s`, `--station` | ICAO station code (e.g., `KJFK`) or 5-digit US ZIP code (e.g., `10001`) | `KJFK` | 
| `--refresh` | Automatic data refresh interval in seconds | `600` | 
| `-h`, `--help` | Show help message and exit | — | 

## Keyboard Controls

While the dashboard is running, use the following shortcuts:

| Key | Action | 
| ----- | ----- | 
| **`1` – `4` + `Enter`** | Open the corresponding NWS / Radar / SPC / AFD quick link in your browser | 
| **`5+` + `Enter`** | Open the details URL for any active weather alert listed in the bottom panel | 
| **`r`** | Manually refresh weather observations, forecast, and alerts immediately | 
| **`q`** | Quit the dashboard (`Ctrl+C` also exits cleanly) | 

## Data Sources

This script uses free, public APIs requiring no API keys:

* **National Weather Service (NWS) API** (`api.weather.gov`) — Point metadata, observations, extended forecasts, and active zone alerts

* **Aviation Weather Center** (`aviationweather.gov`) — ICAO station coordinates and metadata

* **Zippopotam.us** & **OpenStreetMap Nominatim** — US ZIP code to latitude/longitude resolution

## License

MIT License — feel free to modify and share.
