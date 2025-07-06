import requests
import subprocess
import json
import re
import google.generativeai as genai
from datetime import datetime
import psycopg2

GEMINI_API_KEY = "AIzaSyDLcg-O9luxn6HQvZL7nzBKY9VkmgrsEVw"
genai.configure(api_key=GEMINI_API_KEY, transport="rest")

country = "zz"
city_name = "oneshot"
map_name = "new-cairo"
map_bin_path = f"data/system/{country}/{city_name}/maps/{map_name}.bin"

scenario_filename = "generated_abstreet_script.json"


def extract_trip_info(user_text):
    model = genai.GenerativeModel("models/gemini-1.5-pro")
    prompt = f'''
    Extract the structured trip intent from this sentence:

    "{user_text}"

    Return ONLY a valid JSON object with this format:
    {{
      "origin": "string",
      "destination": "string",
      "mode": "Drive" | "Walk" | "Bike",
      "purpose": "Work" | "Meal" | "Recreation"
    }}
    '''
    response = model.generate_content(prompt)
    try:
        match = re.search(r"\{[\s\S]*\}", response.text)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"Error parsing Gemini response: {e}\nRaw: {response.text}")
    return None


def geocode_location(name):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": name, "format": "json", "limit": 1}
    headers = {"User-Agent": "abstreet-gemini-sim"}
    response = requests.get(url, params=params, headers=headers)
    if response.ok and response.json():
        result = response.json()[0]
        return float(result["lon"]), float(result["lat"])
    return None, None


def save_script(script_data, filename=scenario_filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)
    return filename


def import_scenario_via_cli(json_path):
    result = subprocess.run([
        "target/release/cli", "import-scenario",
        "--map", map_bin_path,
        "--input", json_path
    ], capture_output=True, text=True)
    return result.returncode == 0


def load_scenario(scenario_bin_path, edits=None):
    payload = {
        "scenario": scenario_bin_path,
        "modifiers": [],
        "edits": edits
    }
    try:
        response = requests.post("http://127.0.0.1:1234/sim/load", json=payload)
        response.raise_for_status()
        return True
    except:
        return False


def calculate_simulation_target_time(scenario_data):
    latest = max((t.get("departure", 0) for p in scenario_data.get("people", []) for t in p.get("trips", [])), default=0)
    latest += 3600 + 86400
    h, m = divmod(latest, 3600)
    m, s = divmod(m, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}"


def simulate_to_time(target_time):
    try:
        res = requests.get(f"http://127.0.0.1:1234/sim/goto-time?t={target_time}")
        res.raise_for_status()
        return True
    except:
        return False


def fetch_road_thruput():
    try:
        res = requests.get("http://127.0.0.1:1234/data/get-road-thruput")
        res.raise_for_status()
        return set(entry[0] for entry in res.json().get("counts", []))
    except:
        return set()


def fetch_road_details(road_ids):
    details = []
    for rid in sorted(road_ids):
        try:
            res = requests.get(f"http://127.0.0.1:1234/map/get-edit-road-command?id={rid}")
            res.raise_for_status()
            data = res.json()
            lanes = data.get("ChangeRoad", {}).get("new", {}).get("lanes_ltr", [])
            details.append({
                "id": rid,
                "name": data.get("road_name", "Unknown"),
                "lanes": lanes
            })
        except:
            continue
    return details


def fetch_trip_metrics(scenario_name):
    try:
        res = requests.get("http://127.0.0.1:1234/data/get-finished-trips")
        res.raise_for_status()
        trips = res.json()
        durations = [t["duration"] / 60000 for t in trips if t.get("duration")]
        if not durations:
            return None

        def fmt(mins):
            h, m = divmod(int(mins), 60)
            s = int((mins * 60) % 60)
            return f"{h:02}:{m:02}:{s:02}"

        return {
            "avg_travel_time_hms": fmt(sum(durations)/len(durations)),
            "max_delay_hms": fmt(max(durations)),
            "num_trips": len(durations)
        }
    except:
        return None


def insert_simulation_summary_to_db(scenario_name, map_name, metrics_dict, blocked_road_ids=None, user_input=None):
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="traffic_db",
            user="postgres",
            password="117155"
        )
        cur = conn.cursor()
        query = """
            INSERT INTO simulations (
                map_name, user_input, scenario_name,
                avg_travel_time_hms, max_delay_hms, num_trips,
                blocked_roads, run_timestamp
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        blocked = ",".join(str(r) for r in blocked_road_ids) if blocked_road_ids else None
        now = datetime.now()
        cur.execute(query, (
            map_name, user_input, scenario_name,
            metrics_dict["avg_travel_time_hms"],
            metrics_dict["max_delay_hms"],
            metrics_dict["num_trips"],
            blocked, now
        ))
        conn.commit()
    except Exception as e:
        print(f"DB Insert Error: {e}")
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()