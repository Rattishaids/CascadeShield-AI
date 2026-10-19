"""Read-only browser verification of real trained providers and the operator-review boundary."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]
UI='http://127.0.0.1:5173'
API='http://127.0.0.1:8080/api'


def state():
    with urlopen(API+'/state',timeout=30) as response:return json.load(response)


def main():
    before=state()
    if before['status']=='RUNNING':raise RuntimeError('Pause before immutable browser verification; no operator clock command is sent by this script.')
    report={'checkedAtUtc':datetime.now(timezone.utc).isoformat(),'provenance':'BROWSER_ENGINEERING_TEST_EVIDENCE','checks':[],
            'pageErrors':[],'consoleErrors':[],'stateChangingRequests':[],'inferenceRequests':[],'apiErrors':[]}
    allowed={'/api/ml/predict','/api/ml/recommendations/'+before['trucks'][0]['id']} if before['trucks'] else {'/api/ml/predict'}
    def track(request):
        if '/api/' in request.url and request.method not in ('GET','HEAD','OPTIONS'):
            target=request.url.split('127.0.0.1:5173',1)[-1]
            report['inferenceRequests' if target in allowed else 'stateChangingRequests'].append({'url':request.url,'method':request.method})
    def checked(name,**evidence):report['checks'].append({'name':name,'passed':True,**evidence})
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
            page=browser.new_page(viewport={'width':1680,'height':1080})
            page.on('pageerror',lambda error:report['pageErrors'].append(str(error)))
            page.on('console',lambda value:report['consoleErrors'].append(value.text) if value.type=='error' else None)
            page.on('request',track)
            page.on('response',lambda response:report['apiErrors'].append({'url':response.url,'status':response.status}) if '/api/' in response.url and response.status>=400 else None)
            page.goto(UI,wait_until='domcontentloaded')
            expect(page.get_by_text('Backend connected',exact=True)).to_be_visible(timeout=45000)
            page.wait_for_selector('.map-wrap[data-road-network-ready="true"]',timeout=45000)
            checked('backend_and_real_road_map_connected')
            panel=page.get_by_role('region',name='Learned predictions',exact=True)
            for mid,label in [('rule-v1','Rule-based prediction'),('xgb-v1','XGBoost prediction'),('xgb-no-graph-v1','XGBoost prediction'),('gnn-static-v1','GNN prediction'),('gnn-temporal-v1','GNN prediction')]:
                panel.get_by_label('ML prediction source').select_option(mid)
                panel.get_by_role('button',name='Predict current snapshot',exact=True).click()
                expect(panel.locator('.ml-source')).to_contain_text(mid,timeout=30000)
                expect(panel.locator('.ml-source strong')).to_have_text(label)
                expect(panel.get_by_role('table',name='Prediction-time ML outputs')).to_be_visible()
                checked(mid+'_actual_provider_displayed')
            screenshots=ROOT/'reports/screenshots';screenshots.mkdir(parents=True,exist_ok=True)
            panel.screenshot(path=str(screenshots/'milestone4-trained-predictions.png'))
            advice=page.get_by_role('region',name='ML-assisted operator review',exact=True)
            expect(advice).to_be_visible()
            if before['trucks']:
                advice.get_by_role('button',name='Compare operator actions',exact=True).click()
                expect(advice.get_by_text('No incident-response candidate is available.',exact=False)).to_be_visible(timeout=30000)
                expect(advice.get_by_role('button',name='Execute approved action',exact=True)).to_have_count(0)
                checked('completed_live_run_cannot_silently_execute_an_ml_action')
            advice.screenshot(path=str(screenshots/'milestone4-operator-review.png'))
            browser.close()
        after=state()
        assert before==after,'Browser inference altered the saved live scenario'
        assert not any(report[key] for key in ('pageErrors','consoleErrors','apiErrors','stateChangingRequests')),report
        checked('live_state_preserved_without_approval_or_control_requests',runId=before['runId'],clockSec=before['clockSec'],trucks=len(before['trucks']))
        report['passed']=True
    except Exception as error:
        report.update(passed=False,failure=repr(error));raise
    finally:
        report['passedChecks']=len(report['checks'])
        (ROOT/'reports/milestone4_browser_tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(report['checks']),'liveStatePreserved':True}))


if __name__=='__main__':main()
