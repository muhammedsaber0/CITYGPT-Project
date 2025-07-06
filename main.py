# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import json
import requests
import os

from simulator import (
    extract_trip_info, geocode_location, save_script, import_scenario_via_cli,
    load_scenario, calculate_simulation_target_time, simulate_to_time,
    fetch_road_thruput, fetch_trip_metrics, insert_simulation_summary_to_db,
    fetch_road_details
)

app = FastAPI()

# Allow requests from your React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # adjust if your React app runs elsewhere
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

country = "zz"
city_name = "oneshot"
map_name = "newyork"
scenario_name = "natural_lang_trip"
scenario_filename = "generated_abstreet_script.json"

class ScenarioInput(BaseModel):
    user_input: str

class SimulationInput(BaseModel):
    blocked_road_ids: List[int]
    scenario_bin_path: str
    user_input: Optional[str] = None

@app.post("/generate-scenario")
def generate_scenario(data: ScenarioInput):
    try:
        trip_info = extract_trip_info(data.user_input)
        if not trip_info:
            return {"success": False, "message": "Failed to extract trip info from user input."}

        o_lon, o_lat = geocode_location(trip_info["origin"])
        d_lon, d_lat = geocode_location(trip_info["destination"])
        if None in [o_lon, o_lat, d_lon, d_lat]:
            return {"success": False, "message": "Failed to geocode one or more locations."}

        scenario = {
            "scenario_name": scenario_name,
            "people": [{
                "trips": [{
                    "departure": 8000,
                    "origin": {"Position": {"longitude": o_lon, "latitude": o_lat}},
                    "destination": {"Position": {"longitude": d_lon, "latitude": d_lat}},
                    "mode": trip_info.get("mode", "Drive"),
                    "purpose": trip_info.get("purpose", "Work")
                }]
            }]
        }

        json_path = save_script(scenario)
        scenario_bin_path = f"data/system/{country}/{city_name}/scenarios/{map_name}/{scenario_name}.bin"

        if not import_scenario_via_cli(json_path):
            return {"success": False, "message": "Failed to import scenario."}
        if not load_scenario(scenario_bin_path):
            return {"success": False, "message": "Failed to load scenario."}

        target_time = calculate_simulation_target_time(scenario)
        if not simulate_to_time(target_time):
            return {"success": False, "message": "Simulation failed."}

        road_ids = fetch_road_thruput()
        if not road_ids:
            return {"success": False, "message": "No roads detected in scenario."}

        road_details = fetch_road_details(road_ids)
        return {
            "success": True,
            "scenario_bin_path": scenario_bin_path,
            "message": "Scenario generated. Choose roads to block.",
            "roads": road_details
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/simulate-with-blocked-roads")
def simulate_with_blocks(data: SimulationInput):
    try:
        edits = {
            "commands": [],
            "map_name": {"city": {"country": country, "city": city_name}, "map": map_name},
            "version": 1,
            "edits_name": "blocked_roads_batch",
            "proposal_description": []
        }

        for rid in data.blocked_road_ids:
            res = requests.get(f"http://127.0.0.1:1234/map/get-edit-road-command?id={rid}")
            res.raise_for_status()
            road_data = res.json().get("ChangeRoad", {})
            road_data["new"]["lanes_ltr"] = []
            edits["commands"].append({"ChangeRoad": road_data})

        if not load_scenario(data.scenario_bin_path, edits=edits):
            return {"success": False, "message": "Failed to load scenario with edits."}

        with open(scenario_filename, "r") as f:
            scenario_data = json.load(f)
        target_time = calculate_simulation_target_time(scenario_data)
        if not simulate_to_time(target_time):
            return {"success": False, "message": "Simulation after edits failed."}

        metrics = fetch_trip_metrics(scenario_name)
        if not metrics:
            return {"success": False, "message": "Failed to fetch metrics."}

        insert_simulation_summary_to_db(
            scenario_name=scenario_name,
            map_name=map_name,
            metrics_dict=metrics,
            blocked_road_ids=data.blocked_road_ids,
            user_input=data.user_input
        )

        return {"success": True, "metrics": metrics}

    except Exception as e:
        return {"success": False, "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
