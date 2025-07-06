import subprocess
import requests
import json
import re
import sys
import google.generativeai as genai
import psycopg2
from datetime import datetime

# ========== Configuration ==========
GEMINI_API_KEY = "AIzaSyDLcg-O9luxn6HQvZL7nzBKY9VkmgrsEVw"  # Replace with your key
genai.configure(api_key=GEMINI_API_KEY, transport="rest")

# ========== Constants ==========
country = "zz"
city_name = "oneshot"
map_name = "new-cairo"
scenario_filename = "generated_abstreet_script.json"
map_bin_path = f"data/system/{country}/{city_name}/maps/{map_name}.bin"

# ========== Gemini Scenario Generation ==========
def extract_trip_info(user_text):
    model = genai.GenerativeModel("models/gemini-1.5-pro")
    prompt = f"""
Extract the structured trip intent from this sentence:

"{user_text}"

Return ONLY a valid JSON object with this format:
{{
  "origin": "string",
  "destination": "string",
  "mode": "Drive" | "Walk" | "Bike",
  "purpose": "Work" | "Meal" | "Recreation"
}}

No extra text.
"""
    response = model.generate_content(prompt)
    try:
        match = re.search(r"\{[\s\S]*\}", response.text)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"❌ Failed to parse Gemini response: {e}")
        print("Raw output:\n", response.text)
    return None

def geocode_location(name):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": name, "format": "json", "limit": 1}
    headers = {"User-Agent": "abstreet-gemini-sim"}
    response = requests.get(url, params=params, headers=headers)
    if response.ok and response.json():
        result = response.json()[0]
        lon, lat = float(result["lon"]), float(result["lat"])
        print(f"📍 Geocoded '{name}': (lat: {lat}, lon: {lon})")
        return lon, lat
    else:
        print(f"❌ Could not geocode: {name}")
        return None, None

def save_script(script_data, filename=scenario_filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved scenario to {filename}")
    return filename

def generate_scenario_from_prompt():
    print("[*] A/B Street Scenario Generator (Natural Language + Geocoding)")
    user_input = input("📝 Describe your trip (e.g., from Central Park to Times Square by bike for recreation):\n> ")
    trip_info = extract_trip_info(user_input)
    if not trip_info:
        print("❌ Could not extract trip info.")
        return None, None

    origin = trip_info.get("origin")
    dest = trip_info.get("destination")
    mode = trip_info.get("mode", "Drive")
    purpose = trip_info.get("purpose", "Work")

    o_lon, o_lat = geocode_location(origin)
    d_lon, d_lat = geocode_location(dest)

    if None in [o_lon, o_lat, d_lon, d_lat]:
        print("❌ Failed to geocode one or both locations.")
        return None, None

    scenario = {
        "scenario_name": "natural_lang_trip",
        "people": [{
            "trips": [{
                "departure": 8000,
                "origin": {"Position": {"longitude": o_lon, "latitude": o_lat}},
                "destination": {"Position": {"longitude": d_lon, "latitude": d_lat}},
                "mode": mode,
                "purpose": purpose
            }]
        }]
    }

    filename = save_script(scenario)
    return filename, user_input


def import_scenario_via_cli(json_path):
    print("\n📦 Importing scenario...")
    import_result = subprocess.run([
        "target/release/cli", "import-scenario",
        "--map", map_bin_path,
        "--input", json_path
    ], capture_output=True, text=True)

    if import_result.returncode != 0:
        print("❌ Scenario import failed:")
        print(import_result.stderr)
        return False
    print("✅ Scenario imported successfully.")
    return True


def load_scenario(scenario_bin_path, edits=None):
    print("\n🚀 Loading scenario into simulation server...")
    load_payload = {
        "scenario": scenario_bin_path,
        "modifiers": [],
        "edits": edits
    }
    try:
        response = requests.post("http://127.0.0.1:1234/sim/load", json=load_payload)
        response.raise_for_status()
        print("✅ Scenario loaded.")
        return True
    except requests.RequestException as e:
        print("❌ Scenario loading failed:", e)
        return False


def calculate_simulation_target_time(scenario_data):
    latest_departure = max(
        (trip.get("departure", 0)
         for person in scenario_data.get("people", [])
         for trip in person.get("trips", [])),
        default=0
    )
    # Add 1 hour buffer + 1 day (24 hours)
    latest_departure += 3600 + (24 * 3600)

    hours = latest_departure // 3600
    minutes = (latest_departure % 3600) // 60
    seconds = latest_departure % 60
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"


def simulate_to_time(target_time):
    print(f"\n⏱️  Simulating to {target_time}...")
    try:
        sim_response = requests.get(f"http://127.0.0.1:1234/sim/goto-time?t={target_time}")
        sim_response.raise_for_status()
        print("✅ Simulation complete.")
        return True
    except requests.RequestException as e:
        print("❌ Simulation failed:", e)
        return False


def fetch_road_thruput():
    print("\n🛣️  Querying road throughput data...")
    road_ids = set()
    try:
        res = requests.get("http://127.0.0.1:1234/data/get-road-thruput")
        res.raise_for_status()
        for entry in res.json().get("counts", []):
            road_ids.add(entry[0])
        if not road_ids:
            print("❌ No roads used in this scenario.")
            return set()
        print(f"✅ {len(road_ids)} roads used in the scenario.")
        return road_ids
    except Exception as e:
        print("❌ Failed to fetch road throughput data:", e)
        return set()


def build_block_road_edits(road_ids):
    block_road_input = input("\n🛑 Do you want to block road(s)? Enter comma-separated Road IDs or press Enter to skip: ").strip()
    if not block_road_input:
        return None

    try:
        block_road_ids = [int(rid.strip()) for rid in block_road_input.split(",")]
        invalid = [rid for rid in block_road_ids if rid not in road_ids]
        if invalid:
            print(f"⚠️ Invalid Road IDs (not in detected roads): {invalid}")
            return None

        commands = []
        for rid in block_road_ids:
            res = requests.get(f"http://127.0.0.1:1234/map/get-edit-road-command?id={rid}")
            res.raise_for_status()
            change_road = res.json().get("ChangeRoad", {})
            change_road["new"]["lanes_ltr"] = []
            commands.append({"ChangeRoad": change_road})
            print(f"🛑 Road {rid} will be blocked.")

        map_edits = {
            "commands": commands,
            "map_name": {
                "city": {"country": country, "city": city_name},
                "map": map_name
            },
            "version": 1,
            "edits_name": "blocked_roads_batch",
            "proposal_description": []
        }

        return map_edits, block_road_ids  # <-- return both

    except ValueError:
        print("⚠️ Invalid input: Only comma-separated integers are allowed.")
        return None
    except Exception as e:
        print(f"❌ Failed to build road edits: {e}")
        return None


def fetch_and_display_road_info(road_ids):
    print("\n🛣️  Road usage details:")
    print("Detected Road IDs:", sorted(road_ids))
    for rid in sorted(road_ids):
        try:
            res = requests.get(f"http://127.0.0.1:1234/map/get-edit-road-command?id={rid}")
            res.raise_for_status()
            data = res.json()
            change_road = data.get("ChangeRoad", {})
            road_name = data.get("road_name", "Unknown")
            lanes = change_road.get("new", {}).get("lanes_ltr", [])
            descriptions = [
                f"{lane['lt']} ({lane['dir']}, {lane['width'] / 1000:.1f} m)"
                for lane in lanes
            ]
            print(f"  - Road ID {rid} -> Road Name: {road_name}")
            print(f"    Lanes: {', '.join(descriptions) if descriptions else 'None'}")
        except Exception as e:
            print(f"⚠️ Failed to get details for Road ID {rid}: {e}")


def fetch_trip_metrics(scenario_name):
    print("\n📊 Fetching trip metrics...")
    try:
        res = requests.get("http://127.0.0.1:1234/data/get-finished-trips")
        res.raise_for_status()
        trips = res.json()
    except Exception as e:
        print("❌ Failed to retrieve finished trips:", e)
        return None

    durations = [trip["duration"] / 60000 for trip in trips if trip.get("duration")]
    if durations:
        avg = sum(durations) / len(durations)
        max_delay = max(durations)
        count = len(durations)

        def fmt(mins):
            h, m = int(mins // 60), int(mins % 60)
            s = int((mins * 60) % 60)
            return f"{h:02}:{m:02}:{s:02}"

        summary = {
            "avg_travel_time_hms": fmt(avg),
            "max_delay_hms": fmt(max_delay),
            "num_trips": count
        }

        print("\n✅ Metrics summary:")
        print(f"  Simulation ID: {scenario_name}")
        print(f"  Average travel time: {summary['avg_travel_time_hms']}")
        print(f"  Maximum delay: {summary['max_delay_hms']}")
        print(f"  Number of trips: {summary['num_trips']}")

        return summary
    else:
        print("⚠️ No finished trips found.")
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

        insert_query = """
        INSERT INTO simulations (
            map_name,
            user_input,
            scenario_name,
            avg_travel_time_hms,
            max_delay_hms,
            num_trips,
            blocked_roads,
            run_timestamp
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """

        blocked = ",".join(str(rid) for rid in blocked_road_ids) if blocked_road_ids else None
        now = datetime.now()

        cur.execute(insert_query, (
            map_name,
            scenario_name,
            user_input,
            metrics_dict["avg_travel_time_hms"],
            metrics_dict["max_delay_hms"],
            metrics_dict["num_trips"],
            blocked,
            now
        ))

        conn.commit()
        print("✅ Simulation summary inserted into 'simulations' table.")
    except Exception as e:
        print(f"❌ Failed to insert simulation summary: {e}")
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

def fetch_and_display_map_geometry():
    print("\n🗺️  Fetching map geometry...")
    try:
        res = requests.get("http://127.0.0.1:1234/map/get-all-geometry")
        res.raise_for_status()
        geometry = res.json()
        print("✅ Map geometry fetched.")
        print("Geometry details:",  geometry)
        # Optionally, print a summary:
        print(f"  Roads: {len(geometry.get('roads', []))}")
        print(f"  Intersections: {len(geometry.get('intersections', []))}")
        # You can print more details if needed
        return geometry
    except Exception as e:
        print("❌ Failed to fetch map geometry:", e)
        return None


# ========== Main Loop ==========
if __name__ == "__main__":
    print("🌀 A/B Street Scenario Simulator with Gemini (Ctrl+C to quit)")
    # fetch_and_display_map_geometry()
    while True:
        try:
            json_path, user_input = generate_scenario_from_prompt()
            if not json_path:
                continue

            with open(json_path, "r") as f:
                scenario_data = json.load(f)
                scenario_name = scenario_data.get("scenario_name", "natural_lang_trip")

            # Use your previously defined functions here:
            scenario_bin_path = f"data/system/{country}/{city_name}/scenarios/{map_name}/{scenario_name}.bin"
            import_scenario_via_cli(json_path)
            load_scenario(scenario_bin_path, edits=None)

            target_time = calculate_simulation_target_time(scenario_data)
            simulate_to_time(target_time)

            road_ids = fetch_road_thruput()
            if not road_ids:
                continue

            fetch_and_display_road_info(road_ids)
            map_edits, blocked_ids = build_block_road_edits(road_ids)

            if map_edits:
                import_scenario_via_cli(json_path)
                load_scenario(scenario_bin_path, edits=map_edits)
                simulate_to_time(target_time)

            metrics = fetch_trip_metrics(scenario_name)
            if metrics:
                insert_simulation_summary_to_db(
                    scenario_name=scenario_name,
                    map_name=map_name,
                    metrics_dict=metrics,
                    blocked_road_ids=blocked_ids,
                    user_input=user_input
                )



        except KeyboardInterrupt:
            print("\n👋 Exiting simulator. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            continue