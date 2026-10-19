"""Browser evidence for the real-map milestone, never research evaluation data.

Resets only the local simulated fleet. Run after API integration checks, not in
parallel with an operator session. Source files and research tables are untouched.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui', default='http://127.0.0.1:5173')
    parser.add_argument('--api', default='http://127.0.0.1:8080/api')
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/simulator_browser_tests.json')
    parser.add_argument('--screenshot-prefix', default='milestone-1')
    args = parser.parse_args()
    report = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'data_class': 'BROWSER_TEST_EVIDENCE', 'checks': [], 'console_errors': [], 'page_errors': []}
    target = args.report
    target.parent.mkdir(parents=True, exist_ok=True)
    shots = ROOT / 'reports/screenshots'
    shots.mkdir(parents=True, exist_ok=True)

    def api(path, body=None, method=None):
        payload = None if body is None else json.dumps(body, allow_nan=False).encode()
        request = urllib.request.Request(args.api + path, data=payload, method=method or ('POST' if payload else 'GET'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def record(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})
        print('PASS ' + name, flush=True)

    def empty_fleet():
        state = api('/control', {'action': 'RESET'})
        for truck in state['trucks']:
            api('/trucks/' + truck['id'], method='DELETE')

    graph = json.loads((ROOT / 'data/processed/chennai_osm/road_graph.json').read_text(encoding='utf-8'))
    pairs = graph['metadata']['demoPairs'][:3]
    edges = {edge['id']: edge for edge in graph['edges']}
    nodes = {node['id']: node for node in graph['nodes']}
    bbox = graph['bbox']
    def mercator(lat):
        return (1 - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi) / 2

    try:
        empty_fleet()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader'])
            page = browser.new_page(viewport={'width': 1680, 'height': 1080}, device_scale_factor=1)
            page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
            page.on('console', lambda message: report['console_errors'].append(message.text) if message.type == 'error' else None)
            page.goto(args.ui, wait_until='domcontentloaded')
            expect(page.get_by_role('button', name='Backend connected')).to_be_visible(timeout=30000)
            expect(page.locator('.maplibregl-canvas')).to_be_visible(timeout=30000)
            expect(page.locator('.map-wrap')).to_have_attribute('data-road-network-ready', 'true', timeout=30000)
            for label in ('REAL OSM GEOGRAPHY', 'SIMULATED OPERATIONS', 'RULE-BASED ESTIMATE'):
                expect(page.get_by_text(label, exact=True)).to_be_visible()
            record('real map and three provenance labels rendered', network_id=graph['networkId'])

            def map_click(lon, lat):
                canvas = page.locator('.maplibregl-canvas').bounding_box()
                assert canvas
                west, east = (bbox[1] + 180) / 360, (bbox[3] + 180) / 360
                north, south = mercator(bbox[2]), mercator(bbox[0])
                scale = min((canvas['width'] - 92) / (east - west), (canvas['height'] - 92) / (south - north))
                x = canvas['x'] + canvas['width'] / 2 + ((lon + 180) / 360 - (west + east) / 2) * scale
                y = canvas['y'] + canvas['height'] / 2 + (mercator(lat) - (north + south) / 2) * scale
                page.mouse.click(x, y)

            for index, pair in enumerate(pairs, 1):
                page.get_by_role('button', name='Add truck', exact=True).click()
                start, finish = nodes[pair['startNodeId']], nodes[pair['destinationNodeId']]
                map_click(start['longitude'], start['latitude'])
                expect(page.locator('.map-instruction')).to_contain_text('destination')
                map_click(finish['longitude'], finish['latitude'])
                expect(page.get_by_role('button', name='Calculate road route')).to_be_enabled()
                page.get_by_role('button', name='Calculate road route').click()
                expect(page.get_by_text('CONNECTED ROAD ROUTE', exact=True)).to_be_visible(timeout=20000)
                page.get_by_role('button', name='Add truck to fleet').click()
                expect(page.locator('.fleet-card')).to_have_count(index, timeout=20000)
                page.get_by_role('button', name='Close truck details').click()
            state = api('/state')
            assert len(state['trucks']) == 3 and all(t['route']['distanceM'] > 0 for t in state['trucks'])
            assert state['operationsProvenance'] == 'SIMULATED'
            record('three trucks manually created using map picks and valid route previews')
            positions = [t['position'] for t in state['trucks']]
            page.get_by_role('button', name='Start simulation', exact=True).click()
            page.wait_for_timeout(1300)
            page.get_by_role('button', name='Pause', exact=True).click()
            state = api('/state')
            assert state['clockSec'] > 0 and any(t['position'] != pos for t, pos in zip(state['trucks'], positions))
            frozen = state['clockSec']
            page.wait_for_timeout(500)
            assert api('/state')['clockSec'] == frozen
            record('backend-driven movement and pause freeze', clock_sec=frozen)

            route = api('/state')['trucks'][0]['route']['edgeIds']
            preferred = pairs[0]['closurePhysicalId']
            candidates = [edges[e] for e in route if edges[e]['physicalId'] == preferred]
            candidates += sorted([edges[e] for e in route[2:] if edges[e]['physicalId'] != preferred], key=lambda e: -e['lengthM'])
            planned_physical = {edges[e]['physicalId']: edges[e] for e in route[2:]}
            chosen = None
            for edge in candidates[:30]:
                geometry = edge['geometry']
                for fraction in (.5, .3, .7):
                    a, b = geometry[0], geometry[-1]
                    map_click(a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)
                    page.wait_for_timeout(100)
                    panel = page.locator('.chosen-road')
                    if panel.count() and 'OSM segment ' in panel.inner_text():
                        selected_id = panel.inner_text().rsplit('OSM segment ', 1)[1].strip()
                        if selected_id in planned_physical:
                            chosen = planned_physical[selected_id]
                            break
                if chosen:
                    break
            assert chosen, 'Could not select an actual planned road segment by clicking the map'
            page.get_by_label('Duration · simulation minutes').fill('20')
            page.get_by_role('button', name='Inject simulated closure').click()
            expect(page.locator('.decision-card')).not_to_have_count(0, timeout=20000)
            state = api('/state')
            assert state['incidents'][-1]['physicalId'] == chosen['physicalId']
            affected = [t for t in state['trucks'] if t['affectedIncidentIds']]
            assert affected
            card = page.locator('.decision-card').filter(has_text=affected[0]['id']).first
            card.locator('.action-option').filter(has_text='Reroute').click()
            before = next(t for t in state['trucks'] if t['id'] == affected[0]['id'])['position']
            card.get_by_role('button', name='Approve reroute').click()
            page.wait_for_timeout(500)
            state = api('/state')
            approved = next(t for t in state['trucks'] if t['id'] == affected[0]['id'])
            assert approved['position'] == before and approved['reroutes'] == 1
            assert any(event['type'] == 'INTERVENTION_APPROVED' for event in state['events'])
            record('road click injects a closure and manual reroute preserves position', physical_id=chosen['physicalId'], affected_trucks=[t['id'] for t in affected])
            page.screenshot(path=str(shots / f'{args.screenshot_prefix}-intervention.png'), full_page=True)

            scenario_name = 'Browser verified ' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            page.get_by_role('button', name='Scenarios', exact=True).click()
            page.get_by_label('Scenario name').fill(scenario_name)
            page.get_by_role('button', name='Save current scenario').click()
            item = page.locator('.scenario-item').filter(has_text=scenario_name)
            expect(item).to_have_count(1, timeout=20000)
            with page.expect_download() as download_event:
                item.get_by_role('button', name='Export ' + scenario_name).click()
            downloaded = json.loads(Path(download_event.value.path()).read_text())
            assert downloaded['configuration']['operationsProvenance'] == 'SIMULATED'
            item.get_by_role('button', name='Replay', exact=True).click()
            page.wait_for_timeout(400)
            state = api('/state')
            assert state['clockSec'] == 0 and state['replaying'] and state['status'] == 'PAUSED'
            page.get_by_role('button', name='Step forward 30 seconds').click()
            page.wait_for_timeout(500)
            state = api('/state')
            assert state['clockSec'] == 30 and any(t['reroutes'] == 1 for t in state['trucks'])
            record('scenario save, JSON export and scheduled intervention replay via browser', scenario=scenario_name)

            empty_fleet()
            page.reload(wait_until='domcontentloaded')
            expect(page.get_by_role('button', name='Create 20 simulated demo assignments')).to_be_enabled(timeout=30000)
            started = time.monotonic()
            page.get_by_role('button', name='Create 20 simulated demo assignments').click()
            expect(page.locator('.fleet-card')).to_have_count(20, timeout=60000)
            state = api('/state')
            assert len(state['trucks']) == 20 and all(t['route']['distanceM'] > 0 for t in state['trucks'])
            build_sec = time.monotonic() - started
            api('/control', {'action': 'STEP', 'stepSec': 120})
            page.wait_for_timeout(400)
            expect(page.locator('.vehicle-marker')).to_have_count(20, timeout=20000)
            page.get_by_role('button', name='10×', exact=True).click()
            before_clock = api('/state')['clockSec']
            page.get_by_role('button', name='Resume', exact=True).click()
            page.wait_for_timeout(2000)
            page.get_by_role('button', name='Pause', exact=True).click()
            state = api('/state')
            assert state['clockSec'] > before_clock and all(t['distanceTravelledM'] > 0 for t in state['trucks'])
            record('20 connected simulated trucks move with 10x controls', assignment_creation_sec=round(build_sec, 3), simulation_advance_sec=state['clockSec'] - before_clock)
            api('/incidents', {'type': 'CLOSURE', 'physicalId': preferred, 'severity': 1, 'durationSec': 1200})
            page.wait_for_timeout(600)
            page.locator('.fleet-card').first.click()
            page.screenshot(path=str(shots / f'{args.screenshot_prefix}-dashboard.png'), full_page=True)
            assert not report['page_errors'], report['page_errors']
            assert not any('Worker failed' in error for error in report['console_errors']), report['console_errors']
            record('dashboard renders without uncaught JavaScript errors')
            browser.close()
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['error'] = str(error)
        raise
    finally:
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    main()
