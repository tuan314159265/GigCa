"""Export known synthetic anchors and observed train hours without fitting models."""
import hashlib
import json
from pathlib import Path
from datetime import datetime
from .personas import ZONES


def export_catalog(dataset, model_dir):
    dataset, model_dir = Path(dataset), Path(model_dir)
    report = json.loads((model_dir/'report.json').read_text(encoding='utf8'))
    if hashlib.sha256((model_dir/'models.joblib').read_bytes()).hexdigest() != report['artifact_sha256']:
        raise ValueError('Artifact hash mismatch.')
    manifest = json.loads((dataset/'manifest.json').read_text(encoding='utf8'))
    zones = manifest.get('zone_catalog', ZONES)
    hours = set()
    days = set(report['date_splits']['train'])
    for did in report['driver_splits']['train']:
        path = dataset/did/'research_log.json'
        expected = report['input_sha256'].get(str(path.relative_to(dataset)))
        # Reports exported on Windows retain backslashes when loaded on Linux.
        expected = expected or report['input_sha256'].get(f'{did}\\research_log.json')
        if expected != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Training input hash mismatch.')
        log = json.loads(path.read_text(encoding='utf8'))
        for wait in log['wait_spells']:
            dt = datetime.fromisoformat(wait['start'])
            if dt.date().isoformat() in days:
                hours.add(dt.hour)
    catalog = {'kind':'synthetic_research_only', 'artifact_sha256':report['artifact_sha256'],
               'training_hours':sorted(hours),
               'areas':[{'id':f'model_{key}',**value} for key,value in zones.items()],
               'note':'Scenario geographic anchors, not verified waiting/parking places.'}
    (model_dir/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf8')
    return catalog


if __name__ == '__main__':
    import sys
    result = export_catalog(sys.argv[1], sys.argv[2])
    print(json.dumps({'areas':len(result['areas']), 'training_hours':result['training_hours']}))
