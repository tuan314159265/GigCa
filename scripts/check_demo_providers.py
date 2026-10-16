"""Read-only provider smoke check. Never prints keys or authenticated URLs."""
import json
from pathlib import Path
from datetime import datetime, timezone
from api.dashboard import load_local_settings
from api.provider_proxy import read_tomtom_key, request_json, tomtom_url, TOMTOM_ROUTE, TOMTOM_FLOW, search_locations


def main():
    load_local_settings()
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': {}}
    def check(name, fn):
        try:
            detail = fn()
            report['checks'][name] = {'status': 'ok', **detail}
        except Exception as exc:
            report['checks'][name] = {'status': 'error', 'error_type': type(exc).__name__,
                                      'message': str(exc) if isinstance(exc, RuntimeError) else 'Provider check failed; inspect network/certificates.'}
        print(name + ': ' + report['checks'][name]['status'], flush=True)
    def weather():
        data = request_json('https://api.open-meteo.com/v1/forecast?latitude=10.7769&longitude=106.7009&hourly=precipitation,precipitation_probability&forecast_days=1&timezone=UTC')
        if not data.get('hourly', {}).get('time'):
            raise RuntimeError('Weather response has no hourly data.')
        return {'hours': len(data['hourly']['time'])}
    check('weather', weather)
    try:
        read_tomtom_key()
        configured = True
    except RuntimeError:
        configured = False
    report['tomtom_configured'] = configured
    if configured:
        def search():
            result = search_locations('Bến Thành')
            return {'response_received': bool(result)}
        check('tomtom_search', search)
        def routing():
            result = request_json(tomtom_url(TOMTOM_ROUTE + '/10.7769,106.7009:10.772,106.698/json',
                                          {'travelMode': 'motorcycle', 'traffic': 'true'}))
            routes = result.get('routes', [])
            if not routes:
                raise RuntimeError('No route returned.')
            return {'distance_m': routes[0]['summary']['lengthInMeters'],
                    'geometry_points': len(routes[0]['legs'][0]['points'])}
        check('tomtom_routing', routing)
        def traffic():
            data = request_json(tomtom_url(TOMTOM_FLOW, {'point': '10.7769,106.7009', 'unit': 'KMPH'}))
            if 'currentSpeed' not in data.get('flowSegmentData', {}):
                raise RuntimeError('No flow at test point.')
            return {'scope': 'provider segment near test coordinate'}
        check('tomtom_traffic', traffic)
    target = Path('.cache/provider-smoke.json')
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(target)


if __name__ == '__main__':
    main()
