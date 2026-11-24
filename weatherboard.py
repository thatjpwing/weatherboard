#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from threading import Event, Thread
from typing import Optional

import requests
from rich import box
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# NWS API requires a custom User-Agent and Accept headers to bypass 403 blocks
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) WeatherDashboard/1.0",
    "Accept": "application/geo+json, application/json",
}


@dataclass
class StationInfo:
    station_id: str
    name: str
    lat: float
    lon: float
    forecast_url: str
    forecast_zone: str
    radar_station: str
    cwa: str  # 3-letter Forecast Office ID (e.g., TWC, PHI, LAX)


@dataclass
class CurrentWeather:
    temp_f: Optional[float]
    condition: str
    wind_speed: str
    wind_dir: str
    humidity: Optional[float]
    pressure_mb: Optional[float]
    visibility_mi: Optional[float]


@dataclass
class ForecastPeriod:
    name: str
    temp: str
    wind: str
    short_forecast: str


@dataclass
class WeatherAlert:
    event: str
    headline: str
    severity: str
    urgency: str
    url: str

def fetch_json(url: str, headers: Optional[dict] = None) -> Optional[dict]:
    try:
        req_headers = headers if headers is not None else HEADERS
        resp = requests.get(url, headers=req_headers, timeout=8)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def resolve_zip_code(zip_code: str) -> Optional[tuple[float, float, str]]:
    """Resolves a 5-digit US ZIP code to latitude, longitude, and place name."""
    # Method 1: Zippopotam.us (Primary - fast & lightweight US ZIP lookup)
    zip_url = f"http://zippopotam.us/us/{zip_code}"
    zip_data = fetch_json(zip_url, headers={})
    if zip_data and "places" in zip_data and len(zip_data["places"]) > 0:
        place = zip_data["places"][0]
        try:
            lat = float(place["latitude"])
            lon = float(place["longitude"])
            place_name = place.get("place name", "Unknown")
            state = place.get("state abbreviation", "")
            name = f"ZIP {zip_code} ({place_name}, {state})".strip()
            return lat, lon, name
        except (ValueError, KeyError):
            pass

    # Method 2: OpenStreetMap Nominatim (Fallback)
    osm_url = f"https://nominatim.openstreetmap.org/search?postalcode={zip_code}&country=US&format=json"
    osm_data = fetch_json(osm_url, headers={"User-Agent": "WeatherDashboard/1.0"})
    if osm_data and isinstance(osm_data, list) and len(osm_data) > 0:
        res = osm_data[0]
        try:
            lat = float(res["lat"])
            lon = float(res["lon"])
            display_name = res.get("display_name", "").split(",")[0]
            name = f"ZIP {zip_code} ({display_name})"
            return lat, lon, name
        except (ValueError, KeyError):
            pass

    return None

def resolve_station(query: str) -> Optional[StationInfo]:
    """Resolves an ICAO airport code or a 5-digit US ZIP code to NWS weather resources."""
    query = query.strip()
    lat, lon, name = None, None, query.upper()
    station_id = query.upper()

    # Case 1: Input is a 5-digit ZIP code
    if re.fullmatch(r"\d{5}", query):
        zip_res = resolve_zip_code(query)
        if not zip_res:
            return None
        lat, lon, name = zip_res

        # Retrieve NWS point properties to find closest observation station
        point_data = fetch_json(f"https://api.weather.gov/points/{lat},{lon}")
        if not point_data or "properties" not in point_data:
            return None

        p_props = point_data["properties"]
        obs_stations_url = p_props.get("observationStations")
        if obs_stations_url:
            stations_data = fetch_json(obs_stations_url)
            if stations_data and "features" in stations_data and len(stations_data["features"]) > 0:
                station_id = stations_data["features"][0]["properties"].get("stationIdentifier", station_id)

    # Case 2: Input is an ICAO airport code
    else:
        faa_data = fetch_json(f"https://aviationweather.gov/api/data/station?ids={station_id}&format=json")
        if faa_data and isinstance(faa_data, list) and len(faa_data) > 0:
            st_data = faa_data[0]
            lat = st_data.get("lat")
            lon = st_data.get("lon")
            name = st_data.get("site", station_id)

        if lat is None or lon is None:
            nws_st = fetch_json(f"https://api.weather.gov/stations/{station_id}")
            if nws_st and "properties" in nws_st:
                props = nws_st["properties"]
                name = props.get("name", station_id)
                coords = nws_st.get("geometry", {}).get("coordinates", [None, None])
                lon, lat = coords[0], coords[1]

    if lat is None or lon is None:
        return None

    # Step 2: Use coordinates to retrieve NWS forecast grid, warning zone, and CWA office
    point_data = fetch_json(f"https://api.weather.gov/points/{lat},{lon}")
    if not point_data or "properties" not in point_data:
        return None

    p_props = point_data["properties"]
    forecast_url = p_props.get("forecast", "")
    cwa = p_props.get("cwa", "").upper()

    forecast_zone_url = p_props.get("forecastZone", "")
    forecast_zone = forecast_zone_url.split("/")[-1] if forecast_zone_url else ""

    radar_station = station_id[1:] if station_id.startswith("K") and len(station_id) == 4 else station_id

    return StationInfo(
        station_id=station_id,
        name=name,
        lat=lat,
        lon=lon,
        forecast_url=forecast_url,
        forecast_zone=forecast_zone,
        radar_station=radar_station,
        cwa=cwa,
    )


def fetch_current_observation(station_id: str) -> Optional[CurrentWeather]:
    """Fetch latest weather observation from NWS."""
    obs_data = fetch_json(f"https://api.weather.gov/stations/{station_id}/observations/latest")
    if not obs_data or "properties" not in obs_data:
        return None

    props = obs_data["properties"]
    temp_c = props.get("temperature", {}).get("value")
    temp_f = (temp_c * 9 / 5 + 32) if temp_c is not None else None

    humidity = props.get("relativeHumidity", {}).get("value")

    pressure_pa = props.get("barometricPressure", {}).get("value")
    pressure_mb = (pressure_pa / 100) if pressure_pa is not None else None

    vis_m = props.get("visibility", {}).get("value")
    vis_mi = (vis_m / 1609.34) if vis_m is not None else None

    wind_kmh = props.get("windSpeed", {}).get("value")
    wind_mph = f"{int(wind_kmh * 0.621371)} mph" if wind_kmh is not None else "—"

    return CurrentWeather(
        temp_f=temp_f,
        condition=props.get("textDescription", "Clear"),
        wind_speed=wind_mph,
        wind_dir=str(props.get("windDirection", {}).get("value", "") or "—"),
        humidity=humidity,
        pressure_mb=pressure_mb,
        visibility_mi=vis_mi,
    )


def fetch_forecast(forecast_url: str) -> list[ForecastPeriod]:
    """Fetch extended forecast."""
    forecast_periods: list[ForecastPeriod] = []
    if not forecast_url:
        return forecast_periods

    f_data = fetch_json(forecast_url)
    if f_data and "properties" in f_data:
        for p in f_data["properties"].get("periods", [])[:8]:
            forecast_periods.append(
                ForecastPeriod(
                    name=p["name"],
                    temp=f"{p['temperature']}°{p['temperatureUnit']}",
                    wind=f"{p['windSpeed']} {p['windDirection']}",
                    short_forecast=p["shortForecast"],
                )
            )
    return forecast_periods


def fetch_active_alerts(zone_id: str) -> list[WeatherAlert]:
    """Fetch active alerts for the station forecast zone."""
    if not zone_id:
        return []

    url = f"https://api.weather.gov/alerts/active/zone/{zone_id}"
    data = fetch_json(url)
    alerts: list[WeatherAlert] = []

    if data and "features" in data:
        for feature in data["features"]:
            p = feature["properties"]
            alerts.append(
                WeatherAlert(
                    event=p.get("event", "Weather Alert"),
                    headline=p.get("headline", p.get("event", "Active Alert")),
                    severity=p.get("severity", "Unknown"),
                    urgency=p.get("urgency", "Unknown"),
                    url=p.get("affectedZones", ["https://weather.gov"])[0],
                )
            )
    return alerts


def build_current_panel(station: StationInfo, current: Optional[CurrentWeather]) -> Panel:
    table = Table(expand=True, box=box.SIMPLE_HEAVY, show_header=False)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="bold white", justify="right")
    table.add_column("Metric2", style="bold cyan")
    table.add_column("Value2", style="bold white", justify="right")

    if not current:
        table.add_row("Status", "Fetching observation data...", "", "")
    else:
        temp_str = f"{current.temp_f:.1f}°F" if current.temp_f else "—"
        hum_str = f"{current.humidity:.0f}%" if current.humidity else "—"
        press_str = f"{current.pressure_mb:.1f} mb" if current.pressure_mb else "—"
        vis_str = f"{current.visibility_mi:.1f} mi" if current.visibility_mi else "—"

        table.add_row("Temperature", temp_str, "Humidity", hum_str)
        table.add_row("Condition", current.condition, "Barometer", press_str)
        table.add_row("Wind Speed", current.wind_speed, "Visibility", vis_str)

    return Panel(table, title=f"Current Local Conditions ({station.name} - {station.station_id})", border_style="blue")


def build_forecast_panel(forecast: list[ForecastPeriod]) -> Panel:
    table = Table(expand=True, box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Period", width=16, style="yellow")
    table.add_column("Temp", width=10, justify="right", style="bold white")
    table.add_column("Wind", width=14, justify="right", style="dim")
    table.add_column("Forecast", style="white")

    for f in forecast:
        table.add_row(f.name, f.temp, f.wind, f.short_forecast)

    return Panel(table, title="Extended Forecast", border_style="green")


def build_spc_panel(station: StationInfo, alerts: list[WeatherAlert], quick_links: dict[int, tuple[str, str]]) -> Panel:
    table = Table(expand=True, box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("#", width=4, justify="right")
    table.add_column("Key Link / Alert Event", style="bold yellow")
    table.add_column("Details / Status", style="white")

    for key, (title_desc, _) in quick_links.items():
        table.add_row(str(key), f"[Quick Link] {title_desc}", "Press key + Enter to launch browser")

    if alerts:
        start_idx = len(quick_links) + 1
        for idx, alert in enumerate(alerts, start=start_idx):
            style = "red" if alert.severity in ("Severe", "Extreme") else "magenta"
            table.add_row(str(idx), Text(alert.event, style=style), alert.headline[:60] + "...")
    else:
        table.add_row("—", "Active Alerts & Warnings", f"No active NWS warnings for zone {station.forecast_zone}")

    return Panel(table, title="Storm Prediction Center (SPC) & Local Warning Highlights", border_style="magenta")


def build_dashboard(
    station: StationInfo,
    current: Optional[CurrentWeather],
    forecast: list[ForecastPeriod],
    alerts: list[WeatherAlert],
    quick_links: dict[int, tuple[str, str]],
    refresh_seconds: int,
) -> Group:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    title = Text()
    title.append(f" NOAA / NWS Weather Terminal — {station.station_id} ", style="bold white on blue")
    title.append(f" Updated: {now}", style="dim")

    instructions = Text(
        "Type link # and press Enter | r: refresh | q: quit | "
        f"auto-refresh: {refresh_seconds}s",
        style="dim",
    )

    return Group(
        Panel(title, border_style="blue"),
        build_current_panel(station, current),
        build_forecast_panel(forecast),
        build_spc_panel(station, alerts, quick_links),
        instructions,
    )


def open_link(number_buffer: str, quick_links: dict[int, tuple[str, str]], alerts: list[WeatherAlert]) -> None:
    if not number_buffer:
        return
    try:
        num = int(number_buffer)
    except ValueError:
        return

    if num in quick_links:
        webbrowser.open(quick_links[num][1])
    else:
        alert_index = num - (len(quick_links) + 1)
        if 0 <= alert_index < len(alerts):
            webbrowser.open(alerts[alert_index].url)


def keyboard_loop(
    stop_event: Event,
    refresh_event: Event,
    quick_links: dict[int, tuple[str, str]],
    alerts_ref: list[WeatherAlert],
) -> None:
    if sys.platform == "win32":
        import msvcrt

        number_buffer = ""
        while not stop_event.is_set():
            if not msvcrt.kbhit():
                time.sleep(0.05)
                continue

            key = msvcrt.getwch()
            if key.lower() == "q":
                stop_event.set()
                return
            if key.lower() == "r":
                refresh_event.set()
                number_buffer = ""
                continue
            if key.isdigit():
                number_buffer += key
                continue
            if key in ("\r", "\n"):
                open_link(number_buffer, quick_links, alerts_ref)
                number_buffer = ""

    else:
        import select
        import termios
        import tty

        file_descriptor = sys.stdin.fileno()
        old_settings = termios.tcgetattr(file_descriptor)
        number_buffer = ""

        try:
            tty.setcbreak(file_descriptor)
            while not stop_event.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not ready:
                    continue

                key = sys.stdin.read(1)
                if key.lower() == "q":
                    stop_event.set()
                    return
                if key.lower() == "r":
                    refresh_event.set()
                    number_buffer = ""
                    continue
                if key.isdigit():
                    number_buffer += key
                    continue
                if key in ("\r", "\n"):
                    open_link(number_buffer, quick_links, alerts_ref)
                    number_buffer = ""
        finally:
            termios.tcsetattr(file_descriptor, termios.TCSADRAIN, old_settings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Terminal NOAA Weather and SPC Dashboard")
    parser.add_argument(
        "-s",
        "--station",
        type=str,
        default="KJFK",
        help="ICAO Airport/Station Code (e.g., KTUS, KPHL) or 5-digit US ZIP code (e.g., 10001, 85701). Default: KJFK",)
    parser.add_argument(
        "--refresh",
        type=int,
        default=600,
        help="Automatic refresh interval in seconds. Default: 600",
    )
    args = parser.parse_args()

    print(f"Resolving location/station '{args.station}'...")
    station = resolve_station(args.station)
    if not station:
        print(f"Error: Could not resolve station code or ZIP code '{args.station}'.", file=sys.stderr)
        sys.exit(1)

    quick_links = {
        1: (f"{station.name} NWS Forecast", f"https://forecast.weather.gov/MapClick.php?lat={station.lat}&lon={station.lon}"),
        2: (f"{station.radar_station} Live Radar", f"https://radar.weather.gov/station/{station.radar_station}/standard"),
        3: ("Storm Prediction Center (SPC)", "https://www.spc.noaa.gov/"),
        4: (f"{station.cwa} Forecast Discussion (AFD)", f"https://forecast.weather.gov/product.php?site={station.cwa}&product=AFD&issuedby={station.cwa}"),
    }

    current = fetch_current_observation(station.station_id)
    forecast = fetch_forecast(station.forecast_url)
    alerts = fetch_active_alerts(station.forecast_zone)

    stop_event = Event()
    refresh_event = Event()

    alerts_ref: list[WeatherAlert] = []
    alerts_ref.extend(alerts)

    keyboard_thread = Thread(
        target=keyboard_loop,
        args=(stop_event, refresh_event, quick_links, alerts_ref),
        daemon=True,
    )
    keyboard_thread.start()

    with Live(
        build_dashboard(station, current, forecast, alerts_ref, quick_links, args.refresh),
        refresh_per_second=4,
        screen=True,
    ) as live:
        next_refresh = time.monotonic() + args.refresh

        while not stop_event.is_set():
            now = time.monotonic()
            time_until_refresh = next_refresh - now
            timeout = max(0.1, min(0.5, time_until_refresh))

            manually_refreshed = refresh_event.wait(timeout=timeout)
            refresh_event.clear()

            if stop_event.is_set():
                break

            now = time.monotonic()
            if manually_refreshed or now >= next_refresh:
                new_current = fetch_current_observation(station.station_id)
                new_forecast = fetch_forecast(station.forecast_url)
                new_alerts = fetch_active_alerts(station.forecast_zone)

                alerts_ref[:] = new_alerts

                live.update(
                    build_dashboard(
                        station,
                        new_current,
                        new_forecast,
                        alerts_ref,
                        quick_links,
                        args.refresh,
                    )
                )
                next_refresh = time.monotonic() + args.refresh

    print("Exited.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExited.")
