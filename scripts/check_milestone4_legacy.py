"""Rerun existing acquisition/geography/conversion/statistics contracts without changing live operations."""
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def main():
    patterns=('test_data_pipeline.py','test_chennai_network.py','test_graph_snapshot_converter.py','test_benchmark_statistics.py')
    report={'checkedAtUtc':datetime.now(timezone.utc).isoformat(),'provenance':'ENGINEERING_TEST_EVIDENCE','suites':[]}
    for pattern in patterns:
        stream=io.StringIO()
        suite=unittest.TestLoader().discover(str(ROOT/'tests'),pattern=pattern)
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        report['suites'].append({'pattern':pattern,'tests':result.testsRun,'failures':len(result.failures),
                                'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful(),
                                'actualOutput':stream.getvalue()})
    report['tests']=sum(s['tests'] for s in report['suites'])
    report['passed']=all(s['passed'] and s['skipped']==0 for s in report['suites'])
    (ROOT/'reports/milestone4_legacy_python_tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'tests':report['tests']}))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
