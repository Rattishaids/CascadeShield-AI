"""Read-only release browser smoke test, including unavailable OSM raster tiles.

Requires Playwright plus its Chromium browser. Run against a stationary isolated
release instance, not a live demonstration. No reset/control/resource command is
sent. Network routing aborts raster requests before they leave the browser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TILE_HOST = "tile.openstreetmap.org"


def is_tile_url(url: str) -> bool:
    return urlparse(url).hostname == TILE_HOST


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui", default="http://127.0.0.1:5173")
    parser.add_argument("--api", default="http://127.0.0.1:8080/api")
    parser.add_argument("--report", type=Path, default=Path(".runtime/release-browser.json"))
    parser.add_argument("--expect-ml", choices=("off", "on", "auto"), default="off")
    parser.add_argument("--ml-url", default="http://127.0.0.1:8090", help="CPU service URL for --expect-ml on")
    args = parser.parse_args()
    ui, api = args.ui.rstrip("/"), args.api.rstrip("/")
    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    screenshot = report_path.parent / "screenshots" / (report_path.stem + "-offline-map.png")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "checkedAtUtc": datetime.now(timezone.utc).isoformat(),
        "provenance": "RELEASE_BROWSER_ENGINEERING_TEST_EVIDENCE",
        "uiUrl": ui, "apiUrl": api, "expectedMl": args.expect_ml,
        "checks": [], "blockedRasterRequests": [], "expectedTileConsoleErrors": [],
        "unexpectedConsoleErrors": [], "pageErrors": [], "unexpectedRequestFailures": [],
        "apiErrors": [], "stateChangingRequests": [], "inferenceRequests": [],
        "workers": [], "passed": False,
    }

    def checked(name: str, **evidence: object) -> None:
        report["checks"].append({"name": name, "passed": True, **evidence})

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=[
                "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
            ])
            context = browser.new_context(viewport={"width": 1680, "height": 1080})

            def get_json(url: str) -> dict:
                response = context.request.get(url, timeout=60000)
                assert response.ok, f"HTTP {response.status} from {url}"
                return response.json()

            before = get_json(api + "/state")
            assert before["status"] != "RUNNING", "Pause before read-only verification; this script does not send control commands."
            direct_health = get_json(api + "/health")
            proxy_health = get_json(ui + "/api/health")
            assert direct_health.get("status") == proxy_health.get("status") == "UP", (direct_health, proxy_health)
            checked("direct_backend_and_production_frontend_api_proxy_are_healthy")
            if args.expect_ml == "on":
                health = get_json(args.ml_url.rstrip('/') + '/health')
                expected_sha = hashlib.sha256((ROOT / 'models/milestone4/v1/manifest.json').read_bytes()).hexdigest()
                assert health['status'] == 'UP' and health['inferenceDevice'] == 'cpu'
                assert health['selectionManifestSha256'] == expected_sha and not health['trainedOnObservedFreight']
                assert {m['id'] for m in health['models']} == {'xgb-v1','xgb-no-graph-v1','gnn-static-v1','gnn-temporal-v1'}
                checked('four_model_cpu_service_loads_exact_distributed_frozen_manifest', selectionManifestSha256=expected_sha)
            page = context.new_page()

            def abort_raster(route) -> None:
                report["blockedRasterRequests"].append(route.request.url)
                route.abort("internetdisconnected")

            # Exact hostname matching avoids hiding an unrelated failed request.
            context.route(lambda url: is_tile_url(str(url)), abort_raster)
            page.on("pageerror", lambda error: report["pageErrors"].append(str(error)))
            page.on("worker", lambda worker: report["workers"].append(worker.url))

            def console(message) -> None:
                if message.type != "error":
                    return
                item = {"text": message.text, "location": message.location}
                expected = is_tile_url(message.location.get("url", ""))
                report["expectedTileConsoleErrors" if expected else "unexpectedConsoleErrors"].append(item)

            def request_failed(request) -> None:
                if not is_tile_url(request.url):
                    report["unexpectedRequestFailures"].append({"url": request.url, "failure": request.failure})

            def request_sent(request) -> None:
                if urlparse(request.url).path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
                    allowed = urlparse(request.url).path == "/api/ml/predict"
                    report["inferenceRequests" if allowed else "stateChangingRequests"].append({
                        "url": request.url, "method": request.method,
                    })

            page.on("console", console)
            page.on("requestfailed", request_failed)
            page.on("request", request_sent)
            page.on("response", lambda response: report["apiErrors"].append({
                "url": response.url, "status": response.status,
            }) if urlparse(response.url).path.startswith("/api/") and response.status >= 400 else None)
            response = page.goto(ui, wait_until="domcontentloaded", timeout=60000)
            assert response is not None and response.ok, "Production frontend document was not delivered"
            expect(page.get_by_text("Backend connected", exact=True)).to_be_visible(timeout=60000)
            # Source processing/rendering in the bundled worker must succeed while
            # raster requests are already blocked; toggling the basemap is not used.
            roads = page.locator('.map-wrap[data-road-network-ready="true"]')
            roads.wait_for(timeout=60000)
            feature_count = int(roads.get_attribute("data-road-feature-count") or "0")
            assert feature_count > 0, "No actual local vector road features were rendered"
            assert report["blockedRasterRequests"], "No raster requests were intercepted; offline-basemap test did not execute"
            assert report["workers"], "No browser worker was created for real vector processing"
            assert 'still loading' not in roads.inner_text(), 'Raster warning did not reflect the verified rendered road layer'
            checked("worker_backed_local_vector_roads_render_with_osm_raster_network_blocked",
                    renderedRoadFeatures=feature_count, blockedRasterRequests=len(report["blockedRasterRequests"]),
                    workerUrls=report["workers"])
            attribution = page.locator('.maplibregl-ctrl-attrib a[href="https://www.openstreetmap.org/copyright"]')
            assert attribution.count() > 0 and "OpenStreetMap contributors" in (attribution.first.text_content() or ""), "OSM attribution missing from map DOM"
            checked("openstreetmap_attribution_is_preserved_with_unavailable_raster_tiles")

            panel = page.get_by_role("region", name="Learned predictions", exact=True)
            panel.get_by_label("ML prediction source").select_option("rule-v1")
            with page.expect_response(lambda value: urlparse(value.url).path == "/api/ml/predict") as predicted:
                panel.get_by_role("button", name="Predict current snapshot", exact=True).click()
            result = predicted.value.json()
            assert result["prediction"]["source"] == "RULE_BASED" and not result["stateMutated"], result
            expect(panel.locator(".ml-source strong")).to_have_text("Rule-based prediction")
            checked("default_rule_prediction_is_read_only_and_explicitly_labeled")

            panel.get_by_label("ML prediction source").select_option("xgb-v1")
            with page.expect_response(lambda value: urlparse(value.url).path == "/api/ml/predict", timeout=60000) as predicted:
                panel.get_by_role("button", name="Predict current snapshot", exact=True).click()
            learned = predicted.value.json()
            assert not learned["stateMutated"]
            if args.expect_ml == "off":
                assert learned["fallbackUsed"] and learned["prediction"]["source"] == "RULE_BASED", learned
            elif args.expect_ml == "on":
                assert not learned["fallbackUsed"] and learned["prediction"]["modelId"] == "xgb-v1", learned
            if learned["fallbackUsed"]:
                expect(panel.locator(".ml-source strong")).to_have_text("Deterministic fallback")
                assert learned.get("failureReason"), "Fallback has no explicit failure reason"
                for prediction in learned["prediction"]["predictions"]:
                    assert all(prediction.get(field) is None for field in (
                        "etaLowerSec", "etaUpperSec", "slaProbability", "futureImpactProbability",
                    )), "Fallback fabricated a trained probability or calibrated interval"
            else:
                expect(panel.locator(".ml-source strong")).to_have_text("XGBoost prediction")
            checked("learned_request_reports_actual_provider_or_complete_deterministic_fallback",
                    fallbackUsed=learned["fallbackUsed"], actualModel=learned["prediction"]["modelId"],
                    source=learned["prediction"]["source"])
            if args.expect_ml == 'on':
                for model_id in ('xgb-no-graph-v1', 'gnn-static-v1', 'gnn-temporal-v1'):
                    panel.get_by_label('ML prediction source').select_option(model_id)
                    with page.expect_response(lambda response: urlparse(response.url).path == '/api/ml/predict', timeout=60000) as response:
                        panel.get_by_role('button', name='Predict current snapshot', exact=True).click()
                    value = response.value.json()
                    assert not value['fallbackUsed'] and not value['stateMutated'], value.get('failureReason')
                    assert value['prediction']['modelId'] == model_id and value['prediction']['source'] == 'TRAINED_SIMULATION_MODEL'
                    expect(panel.locator('.ml-source strong')).to_have_text('GNN prediction' if model_id.startswith('gnn') else 'XGBoost prediction')
                    for row in value['prediction']['predictions']:
                        for field in ('remainingArrivalSec','etaLowerSec','etaUpperSec','slaProbability','futureImpactProbability'):
                            assert row.get(field) is None or math.isfinite(row[field])
                        for field in ('slaProbability','futureImpactProbability'):
                            assert row.get(field) is None or 0 <= row[field] <= 1
                    checked(model_id+'_actual_cpu_prediction_is_displayed', source=value['prediction']['source'])
            page.screenshot(path=str(screenshot), full_page=True)
            report["screenshot"] = str(screenshot.relative_to(ROOT)) if screenshot.is_relative_to(ROOT) else str(screenshot)
            after = get_json(api + "/state")
            assert before == after, "Read-only browser verification changed stationary authoritative state"
            checked("stationary_live_state_preserved_without_control_or_approval_requests",
                    runId=before.get("runId"), clockSec=before["clockSec"], truckCount=len(before["trucks"]))
            for key in ("pageErrors", "unexpectedConsoleErrors", "unexpectedRequestFailures", "apiErrors", "stateChangingRequests"):
                assert not report[key], f"Unexpected browser errors/requests in {key}: {report[key]}"
            checked("no_unexpected_console_page_api_or_state_changing_activity")
            browser.close()
        report["passed"] = True
    except Exception as error:
        report["failure"] = repr(error)
    finally:
        report["passedChecks"] = len(report["checks"])
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": report["passedChecks"], "report": str(report_path)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
