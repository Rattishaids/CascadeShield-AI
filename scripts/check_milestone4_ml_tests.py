"""Record actual ML/audit contract tests in the isolated CPU environment, without fitting."""
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    result={'checkedAtUtc':datetime.now(timezone.utc).isoformat(),'provenance':'ENGINEERING_TEST_EVIDENCE','suites':[]}
    for pattern in ('test_ml*.py','test_milestone4*.py'):
        stream=io.StringIO();suite=unittest.TestLoader().discover(str(ROOT/'tests'),pattern=pattern)
        run=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        result['suites'].append({'pattern':pattern,'tests':run.testsRun,'failures':len(run.failures),'errors':len(run.errors),
                                 'skipped':len(run.skipped),'passed':run.wasSuccessful(),'actualOutput':stream.getvalue()})
    result['passed']=all(s['passed'] and s['skipped']==0 for s in result['suites'])
    result['tests']=sum(s['tests'] for s in result['suites'])
    (ROOT/'reports/milestone4_ml_unit_tests.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'tests':result['tests']}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
