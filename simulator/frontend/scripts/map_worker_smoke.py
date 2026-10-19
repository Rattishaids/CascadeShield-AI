"""Read-only live Chromium verification of real MapLibre roads, routes, and road selection.

Requires the running simulator with at least one manually configured/saved truck.
Never submits truck, control, incident, or decision mutations to the backend.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


def get_json(url: str) -> dict:
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5173/")
    parser.add_argument("--api", default="http://127.0.0.1:8080/api")
    parser.add_argument("--output", type=Path, default=Path("smoke-output/map-worker.json"))
    args = parser.parse_args()
    network = get_json(f"{args.api}/network")
    state = get_json(f"{args.api}/state")
    if not state["trucks"]:
        raise SystemExit("Create at least one real-network simulated truck before verifying route rendering.")
    road_ids = {feature["properties"]["physicalId"] for feature in get_json(f"{args.api}/network/roads")["features"]}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_selector('.map-wrap[data-road-network-ready="true"]', timeout=45000)
        page.wait_for_function('Number(document.querySelector(".map-wrap")?.dataset.routeFeatureCount)>0', timeout=20000)
        result = page.locator(".map-wrap").evaluate("(element)=>({roadHitFeatures:Number(element.dataset.roadFeatureCount),routeFeatures:Number(element.dataset.routeFeatureCount),roadNetworkReady:element.dataset.roadNetworkReady})")

        # The bbox fit is projected to a screen point near a documented real road.
        # Selection may return a neighbouring road within the hit radius; it must be
        # a physical segment actually present in the backend's imported GeoJSON.
        box = page.locator(".map-canvas").bounding_box()
        assert box is not None
        south, west, north, east = network["bbox"]

        def mercator(latitude: float) -> float:
            return math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2)) / (2 * math.pi)

        low, high = mercator(south), mercator(north)
        scale = min((box["width"] - 92) / ((east - west) / 360), (box["height"] - 92) / (high - low))
        longitude, latitude = network["metadata"]["demoPairs"][0]["closureMidpoint"]
        x = box["width"] / 2 + (longitude - (west + east) / 2) / 360 * scale
        y = box["height"] / 2 - (mercator(latitude) - (low + high) / 2) * scale
        page.mouse.click(box["x"] + x, box["y"] + y)
        page.wait_for_selector(".incident-builder", timeout=5000)
        selection = page.locator(".chosen-road").inner_text()
        physical_id = selection.split("OSM segment ", 1)[1].strip()
        result.update({"networkId": network["networkId"], "backendTruckCount": len(state["trucks"]), "selectedRoad": selection, "selectionExistsInRealGraph": physical_id in road_ids, "workerErrors": [error for error in errors if "worker" in error.lower()], "consoleErrors": errors, "warnings": page.locator(".map-warning").all_text_contents()})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(args.output.with_suffix(".png")), full_page=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        browser.close()
    print(json.dumps(result, indent=2))
    assert result["roadHitFeatures"] > 0 and result["routeFeatures"] > 0
    assert result["selectionExistsInRealGraph"]
    assert not result["workerErrors"]


if __name__ == "__main__":
    main()
