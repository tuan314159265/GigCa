"""Local end-to-end HTTP smoke: BFF cookie auth, isolated synthetic demo, personal live request."""
import json
import secrets
from pathlib import Path
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError


def main():
    base = 'http://127.0.0.1:3000'
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    def call(path, body=None, method=None):
        headers = {'Content-Type': 'application/json', 'Origin': base}
        request = Request(base + path, json.dumps(body).encode() if body is not None else None,
                          headers, method=method or ('POST' if body is not None else 'GET'))
        with opener.open(request, timeout=60) as response:
            return json.load(response)
    try:
        call('/api/v1/research/drivers')
        raise AssertionError('Research endpoint must require authentication')
    except HTTPError as exc:
        assert exc.code == 401
    credentials_file = Path('.cache/demo-account.json')
    if credentials_file.exists():
        credentials = json.loads(credentials_file.read_text())
    else:
        credentials = {'username': 'gigca_demo_' + secrets.token_hex(3), 'password': secrets.token_urlsafe(20)}
        call('/api/v1/auth/register', {**credentials, 'display_name': 'Demo nghiên cứu'})
        credentials_file.write_text(json.dumps(credentials), encoding='utf8')
    login = call('/api/v1/auth/login', credentials)
    assert 'token' not in login, 'BFF must keep bearer token out of JSON'
    assert any(c.name == 'gigca_driver_session' and c.has_nonstandard_attr('HttpOnly') for c in jar)
    before = call('/api/v1/me/trips')['total']
    drivers = call('/api/v1/research/drivers')['drivers']
    research = call('/api/v1/research/recommendations', {'driver_id': 'D001'})
    assert research['snapshot']['mode'] == 'research'
    assert call('/api/v1/me/trips')['total'] == before == 0
    session = call('/api/v1/sessions', {})
    update = call('/api/v1/sessions/' + session['session_id'] + '/context', {
        'context_version': session['context_version'], 'current_lat': 10.7769, 'current_lng': 106.7009,
        'idle_duration_min': 15, 'horizon_min': 60, 'max_reposition_km': 3}, method='PATCH')
    live = call('/api/v1/recommendations', {'session_id': session['session_id'], 'context_version': update['context_version']})
    report = {'cookie_auth': True, 'research_drivers': len(drivers), 'research_ml': research['ml_insights'] is not None,
              'real_history_unchanged': True, 'personal_mode': live['snapshot']['mode'],
              'live_weather_hours': len(live['weather']), 'live_sources': live['snapshot']['sources'],
              'live_objectives': {k: v['status'] for k, v in live['objectives'].items()}}
    Path('.cache/app-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k != 'live_sources'}, ensure_ascii=False))
    print('Local test credentials: .cache/demo-account.json (not a real driver account)')


if __name__ == '__main__':
    main()
