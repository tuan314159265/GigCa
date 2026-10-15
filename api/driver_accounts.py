"""Driver accounts and owner-scoped personal history on the existing SQLite database."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import secrets
import sqlite3
import time
import uuid

from api.errors import ApiError
from data.driver_log_import import validate_profile, validate_trips, validate_waits

PASSWORD_ITERATIONS = 600_000
TOKEN_TTL = 7 * 86400
MAX_IMPORT_ROWS = 2000


class DriverAccounts:
    def init_accounts(self, db):
        db.executescript("""
        CREATE TABLE IF NOT EXISTS drivers(
          id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, display_name TEXT NOT NULL,
          created REAL NOT NULL, profile TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS driver_tokens(
          token_hash TEXT PRIMARY KEY, driver_id TEXT NOT NULL REFERENCES drivers(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS driver_sessions(
          session_id TEXT PRIMARY KEY REFERENCES sessions(id), driver_id TEXT NOT NULL REFERENCES drivers(id));
        CREATE INDEX IF NOT EXISTS driver_sessions_owner ON driver_sessions(driver_id);
        CREATE TABLE IF NOT EXISTS driver_records(
          driver_id TEXT NOT NULL REFERENCES drivers(id), kind TEXT NOT NULL CHECK(kind IN ('trips','waits')),
          record_id TEXT NOT NULL, occurred_at TEXT NOT NULL, payload TEXT NOT NULL,
          imported_at REAL NOT NULL, PRIMARY KEY(driver_id, kind, record_id));
        CREATE INDEX IF NOT EXISTS driver_records_time ON driver_records(driver_id, kind, occurred_at);
        CREATE TABLE IF NOT EXISTS driver_imports(
          id TEXT PRIMARY KEY, driver_id TEXT NOT NULL REFERENCES drivers(id),
          created REAL NOT NULL, confirmed REAL, payload TEXT NOT NULL, report TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_attempts(bucket TEXT NOT NULL, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS auth_attempts_bucket ON auth_attempts(bucket, created);
        """)

    @staticmethod
    def _credentials(payload):
        if set(payload) - {'username', 'password', 'display_name'}:
            raise ApiError(422, 'invalid_credentials', 'Có trường đăng nhập không hỗ trợ.')
        username, password = payload.get('username'), payload.get('password')
        if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,64}', username):
            raise ApiError(422, 'invalid_username', 'Tên đăng nhập gồm 3–64 chữ, số hoặc ký tự _ . -')
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise ApiError(422, 'invalid_password', 'Mật khẩu cần từ 12 đến 128 ký tự.')
        return username.lower(), password

    @staticmethod
    def _password(password, salt=None, iterations=None):
        iterations = PASSWORD_ITERATIONS if iterations is None else iterations
        salt = salt or secrets.token_hex(16)
        value = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), iterations).hex()
        return f'pbkdf2_sha256${iterations}${salt}${value}'

    def _auth_limit(self, client, username):
        # Count before hashing, including unknown users and account creation.
        now = time.time()
        buckets = [(self.hash('ip:' + client), 60), (self.hash('user:' + username), 10)]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM auth_attempts WHERE created < ?', (now - 900,))
            for bucket, limit in buckets:
                count = db.execute('SELECT count(*) FROM auth_attempts WHERE bucket=?', (bucket,)).fetchone()[0]
                if count >= limit:
                    raise ApiError(429, 'auth_rate_limit', 'Thử đăng nhập quá nhiều lần. Vui lòng chờ 15 phút.')
            db.executemany('INSERT INTO auth_attempts VALUES(?,?)', [(bucket, now) for bucket, _ in buckets])

    @staticmethod
    def _driver_public(row):
        return {key: row[key] for key in ('id', 'username', 'display_name', 'created')}

    def register(self, payload, client='local'):
        username, password = self._credentials(payload)
        name = payload.get('display_name', username)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ApiError(422, 'invalid_name', 'Tên hiển thị cần từ 1 đến 100 ký tự.')
        self._auth_limit(client, username)
        encoded = self._password(password)
        try:
            with self.db() as db:
                did = str(uuid.uuid4())
                db.execute('INSERT INTO drivers(id,username,password_hash,display_name,created) VALUES(?,?,?,?,?)',
                           (did, username, encoded, name.strip(), time.time()))
        except sqlite3.IntegrityError:
            raise ApiError(409, 'username_taken', 'Tên đăng nhập đã được sử dụng.') from None
        return self.login({'username': username, 'password': password}, client, count_attempt=False)

    def login(self, payload, client='local', *, count_attempt=True):
        username, password = self._credentials(payload)
        if count_attempt:
            self._auth_limit(client, username)
        with self.db() as db:
            row = db.execute('SELECT * FROM drivers WHERE username=?', (username,)).fetchone()
            encoded = row['password_hash'] if row else f'pbkdf2_sha256${PASSWORD_ITERATIONS}${"00" * 16}${"00" * 32}'
            _, iterations, salt, _ = encoded.split('$')
            candidate = self._password(password, salt, int(iterations))
            if not secrets.compare_digest(candidate, encoded) or row is None:
                raise ApiError(401, 'invalid_credentials', 'Tên đăng nhập hoặc mật khẩu không đúng.')
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM driver_tokens WHERE expires<=?', (time.time(),))
            db.execute('INSERT INTO driver_tokens VALUES(?,?,?)', (self.hash(token), row['id'], time.time() + TOKEN_TTL))
            return {'driver': self._driver_public(row), 'token': token, 'token_type': 'Bearer', 'expires_in_s': TOKEN_TTL}

    def account(self, db, token):
        row = db.execute('''SELECT d.* FROM drivers d JOIN driver_tokens t ON t.driver_id=d.id
                          WHERE t.token_hash=? AND t.expires>?''', (self.hash(token), time.time())).fetchone()
        if row is None:
            raise ApiError(401, 'login_required', 'Cần đăng nhập hoặc phiên đăng nhập đã hết hạn.')
        return row

    def me(self, token):
        with self.db() as db:
            return self._driver_public(self.account(db, token))

    def logout(self, token):
        with self.db() as db:
            self.account(db, token)
            db.execute('DELETE FROM driver_tokens WHERE token_hash=?', (self.hash(token),))
        return {'logged_out': True}

    def profile(self, token, payload=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.account(db, token)
            profile = json.loads(row['profile'])
            if payload is not None:
                if not isinstance(payload, dict) or any(k.startswith('_') for k in payload):
                    raise ApiError(422, 'invalid_profile', 'Hồ sơ không hợp lệ.')
                clean, problems = validate_profile(payload)
                if problems or any(isinstance(v, bool) for v in payload.values()):
                    raise ApiError(422, 'invalid_profile', '; '.join(problems) or 'Giá trị hồ sơ phải là số.')
                profile.update(clean)
                for key, value in payload.items():
                    if value is None:
                        profile.pop(key, None)
                db.execute('UPDATE drivers SET profile=? WHERE id=?', (json.dumps(profile), row['id']))
            return {'driver_id': row['id'], 'profile': profile}

    @staticmethod
    def _rows(payload, name):
        value = payload.get(name, [])
        if isinstance(value, str):
            value = list(csv.DictReader(io.StringIO(value.lstrip('\ufeff'))))
        if not isinstance(value, list) or len(value) > MAX_IMPORT_ROWS or not all(isinstance(r, dict) for r in value):
            raise ApiError(422, 'invalid_import', f'{name}: tối đa {MAX_IMPORT_ROWS} dòng JSON hoặc chuỗi CSV.')
        return value

    def preview_import(self, token, payload):
        if set(payload) - {'trips', 'wait_spells', 'consent_reference', 'collected_via'}:
            raise ApiError(422, 'invalid_import', 'Có trường import không hỗ trợ; tài xế được xác định bằng token.')
        provenance = {}
        for key in ('consent_reference', 'collected_via'):
            value = payload.get(key)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 500:
                raise ApiError(422, 'consent_required', 'Cần tham chiếu đồng ý và cách thu thập nhật ký thật.')
            provenance[key] = value.strip()
        trips, waits = self._rows(payload, 'trips'), self._rows(payload, 'wait_spells')
        if not trips and not waits:
            raise ApiError(422, 'empty_import', 'Chưa có nhật ký để nhập.')
        report, accepted = {}, {}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            driver = self.account(db, token)
            for kind, rows, validator, id_key in (
                ('trips', trips, validate_trips, 'trip_id'), ('waits', waits, validate_waits, 'spell_id')
            ):
                clean, rejected, warnings = validator(rows)
                existing = {r['record_id'] for r in db.execute(
                    'SELECT record_id FROM driver_records WHERE driver_id=? AND kind=?', (driver['id'], kind))}
                duplicates = [r[id_key] for r in clean if r[id_key] in existing]
                accepted[kind] = [r for r in clean if r[id_key] not in existing]
                report[kind] = {'rows': len(rows), 'accepted': len(accepted[kind]),
                                'rejected': rejected, 'warnings': warnings, 'duplicate_ids': duplicates}
            iid = str(uuid.uuid4())
            prepared = {**accepted, 'provenance': provenance}
            db.execute('DELETE FROM driver_imports WHERE confirmed IS NULL AND created<?', (time.time() - 86400,))
            db.execute('INSERT INTO driver_imports VALUES(?,?,?,NULL,?,?)',
                       (iid, driver['id'], time.time(), json.dumps(prepared), json.dumps(report)))
        return {'import_id': iid, 'report': report, 'requires_confirmation': True}

    def confirm_import(self, token, iid):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            driver = self.account(db, token)
            row = db.execute('SELECT * FROM driver_imports WHERE id=? AND driver_id=?', (iid, driver['id'])).fetchone()
            if row is None:
                raise ApiError(404, 'import_not_found', 'Không tìm thấy bản nhập của tài xế.')
            if row['confirmed'] is not None:
                return {'import_id': iid, 'confirmed': True, 'report': json.loads(row['report'])}
            if row['created'] < time.time() - 86400:
                raise ApiError(410, 'import_expired', 'Bản xem trước đã hết hạn; vui lòng nhập lại.')
            prepared, report = json.loads(row['payload']), json.loads(row['report'])
            for kind, id_key, date_key in (('trips', 'trip_id', 'started_at'), ('waits', 'spell_id', 'start')):
                inserted, duplicate_ids = 0, []
                for record in prepared[kind]:
                    cursor = db.execute('INSERT OR IGNORE INTO driver_records VALUES(?,?,?,?,?,?)',
                        (driver['id'], kind, record[id_key], record[date_key], json.dumps(record), time.time()))
                    inserted += cursor.rowcount
                    if not cursor.rowcount:
                        duplicate_ids.append(record[id_key])
                report[kind].update({'inserted': inserted, 'duplicates_at_confirmation': duplicate_ids})
            db.execute('UPDATE driver_imports SET confirmed=?,report=? WHERE id=?', (time.time(), json.dumps(report), iid))
        return {'import_id': iid, 'confirmed': True, 'report': report}

    @staticmethod
    def _page(limit, offset):
        try:
            limit, offset = int(limit), int(offset)
        except (ValueError, TypeError):
            raise ApiError(422, 'invalid_page', 'Phân trang không hợp lệ.') from None
        if not 1 <= limit <= 100 or not 0 <= offset <= 1_000_000:
            raise ApiError(422, 'invalid_page', 'limit từ 1–100; offset không âm.')
        return limit, offset

    def records(self, token, kind, limit=20, offset=0):
        if kind not in ('trips', 'waits'):
            raise ApiError(404, 'not_found', 'Loại lịch sử không hỗ trợ.')
        limit, offset = self._page(limit, offset)
        with self.db() as db:
            did = self.account(db, token)['id']
            total = db.execute('SELECT count(*) FROM driver_records WHERE driver_id=? AND kind=?', (did, kind)).fetchone()[0]
            rows = db.execute('''SELECT payload FROM driver_records WHERE driver_id=? AND kind=?
                                ORDER BY julianday(occurred_at) DESC, record_id DESC LIMIT ? OFFSET ?''',
                              (did, kind, limit, offset)).fetchall()
        return {'items': [json.loads(r['payload']) for r in rows], 'total': total, 'limit': limit, 'offset': offset}

    def data_status(self, token):
        with self.db() as db:
            did = self.account(db, token)['id']
            counts = {r['kind']: r['n'] for r in db.execute(
                'SELECT kind,count(*) AS n FROM driver_records WHERE driver_id=? GROUP BY kind', (did,))}
        return {'trips': counts.get('trips', 0), 'wait_spells': counts.get('waits', 0),
                'engine_history_limit_per_kind': 5000,
                'model_status': 'not_evaluated',
                'note': 'Số dòng lịch sử không chứng minh model đủ điều kiện. Engine kiểm tra chất lượng và backtest khi tính gợi ý.'}

    def driver_history(self, token, limit=20, offset=0, rid=None):
        limit, offset = self._page(limit, offset)
        with self.db() as db:
            did = self.account(db, token)['id']
            if rid is not None:
                row = db.execute('''SELECT r.result FROM runs r JOIN driver_sessions s ON r.session_id=s.session_id
                                    WHERE s.driver_id=? AND r.id=?''', (did, rid)).fetchone()
                if row is None:
                    raise ApiError(404, 'not_found', 'Không tìm thấy lịch sử của tài xế.')
                return json.loads(row['result'])
            total = db.execute('''SELECT count(*) FROM runs r JOIN driver_sessions s ON r.session_id=s.session_id
                                 WHERE s.driver_id=?''', (did,)).fetchone()[0]
            rows = db.execute('''SELECT r.id,r.created,r.result FROM runs r
                                 JOIN driver_sessions s ON r.session_id=s.session_id WHERE s.driver_id=?
                                 ORDER BY r.created DESC,r.id DESC LIMIT ? OFFSET ?''', (did, limit, offset)).fetchall()
            items = []
            for row in rows:
                result = json.loads(row['result'])
                items.append({'id': row['id'], 'created': row['created'],
                              'input_used': result.get('input_used'), 'snapshot': result.get('snapshot'),
                              'direction_priority': result.get('direction_priority')})
        return {'items': items, 'total': total, 'limit': limit, 'offset': offset}

    def personal_input(self, db, sid):
        owner = db.execute('SELECT driver_id FROM driver_sessions WHERE session_id=?', (sid,)).fetchone()
        if owner is None:
            return None
        driver = db.execute('SELECT profile FROM drivers WHERE id=?', (owner['driver_id'],)).fetchone()
        data = {'driver_profile': json.loads(driver['profile']), 'trip_log': [], 'wait_spells': []}
        for kind, key in (('trips', 'trip_log'), ('waits', 'wait_spells')):
            rows = db.execute('''SELECT payload FROM driver_records WHERE driver_id=? AND kind=?
                                ORDER BY julianday(occurred_at) DESC, record_id DESC LIMIT 5000''',
                              (owner['driver_id'], kind)).fetchall()
            data[key] = [json.loads(r['payload']) for r in reversed(rows)]
        return data
