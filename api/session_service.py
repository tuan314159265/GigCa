"""Persistent local v1 service; provider/engine logic stays in the existing adapter."""
from __future__ import annotations
import hashlib
import json
import math
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from api.dashboard import recommend, ROOT

class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code = status, code
        super().__init__(message)

class Backend:
    def __init__(self, path=None):
        self.path = str(path or os.environ.get('GIGCA_SESSION_DB', '.cache/backend.sqlite3'))
        if not Path(self.path).is_absolute():
            self.path = str(ROOT / self.path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL,
              expires REAL NOT NULL, version INTEGER NOT NULL, context TEXT NOT NULL, waiting REAL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
              created REAL NOT NULL, context TEXT NOT NULL, result TEXT NOT NULL,
              idem TEXT, payload_hash TEXT, UNIQUE(session_id, idem));
            ''')
    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()
    def create(self):
        sid, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',
                       (sid, self.hash(token), time.time()+86400, 0, '{}', None))
        return {'session_id':sid, 'token':token, 'context_version':0, 'expires_in_s':86400}
    @staticmethod
    def hash(value):
        return hashlib.sha256(value.encode()).hexdigest()
    def session(self, db, sid, token):
        row = db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
        if not row or row['expires'] <= time.time() or not secrets.compare_digest(row['token_hash'], self.hash(token)):
            raise ApiError(401, 'invalid_session', 'Phiên không hợp lệ hoặc đã hết hạn.')
        return row
    def update(self, sid, token, payload):
        allowed = {'current_lat':(-90,90), 'current_lng':(-180,180), 'idle_duration_min':(0,1440),
                   'horizon_min':(1,480), 'max_reposition_km':(0,50)}
        if set(payload)-set(allowed)-{'rain_tolerance_level','context_version'}:
            raise ApiError(422,'invalid_context','Có trường ngữ cảnh không hỗ trợ.')
        for key,(lo,hi) in allowed.items():
            if key in payload:
                v=payload[key]
                if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not lo<=v<=hi:
                    raise ApiError(422,'invalid_context',f'{key} không hợp lệ.')
                if key in ('idle_duration_min','horizon_min') and v!=int(v):
                    raise ApiError(422,'invalid_context',f'{key} phải là số nguyên.')
        if payload.get('rain_tolerance_level','medium') not in ('low','medium','high'):
            raise ApiError(422,'invalid_context','Mức chịu mưa không hợp lệ.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self.session(db,sid,token)
            if payload.get('context_version') != row['version']:
                raise ApiError(409,'context_conflict','Ngữ cảnh đã thay đổi. Tải lại trước khi cập nhật.')
            ctx=json.loads(row['context']);ctx.update({k:v for k,v in payload.items() if k!='context_version'})
            db.execute('UPDATE sessions SET context=?, version=version+1 WHERE id=?',(json.dumps(ctx),sid))
        return {'context':ctx,'context_version':row['version']+1}
    def run(self, sid, token, payload, idem=None):
        if set(payload)-{'session_id','context_version'}:
            raise ApiError(422,'invalid_request','Nguồn dữ liệu do server cấu hình.')
        digest=self.hash(json.dumps(payload,sort_keys=True))
        with self.db() as db:
            row=self.session(db,sid,token)
            if idem:
                old=db.execute('SELECT * FROM runs WHERE session_id=? AND idem=?',(sid,idem)).fetchone()
                if old:
                    if old['payload_hash']!=digest:raise ApiError(409,'idempotency_conflict','Key đã được dùng cho input khác.')
                    return json.loads(old['result'])
            if payload.get('context_version')!=row['version']:
                raise ApiError(409,'context_conflict','Ngữ cảnh đã thay đổi.')
            ctx=json.loads(row['context'])
        if 'current_lat' not in ctx or 'current_lng' not in ctx:
            raise ApiError(422,'origin_required','Cần vị trí hiện tại để tính gợi ý.')
        context={'idle_duration_min':15,'horizon_min':60,'max_reposition_km':3,
                 **{k:v for k,v in ctx.items() if k!='rain_tolerance_level'}}
        if row['waiting'] is not None:context['idle_duration_min']=min(1440,int((time.time()-row['waiting'])/60))
        mode=os.environ.get('GIGCA_DATA_MODE','live')
        raw=recommend({'mode':mode,'context':context,'rain_tolerance_level':ctx.get('rain_tolerance_level','medium')}, include_snapshot=True)
        snapshot=raw.pop('_input_snapshot')
        rid=str(uuid.uuid4())
        output={**raw,'recommendation_id':rid,'context_version':row['version'],
                'input_used':context,'is_demo':mode=='simulation','evaluated_at':time.time(),
                'config_hash':self.hash((ROOT / 'config/engine_config.json').read_text(encoding='utf-8')),
                'engine_version':self.hash(''.join(p.read_text(encoding='utf-8') for p in sorted((ROOT / 'engine/src').rglob('*.py'))))}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            latest=self.session(db,sid,token)
            if latest['version']!=row['version']:raise ApiError(409,'context_conflict','Vị trí thay đổi trong khi tính gợi ý.')
            if idem:
                old=db.execute('SELECT * FROM runs WHERE session_id=? AND idem=?',(sid,idem)).fetchone()
                if old:
                    if old['payload_hash']!=digest:raise ApiError(409,'idempotency_conflict','Key trùng input khác.')
                    return json.loads(old['result'])
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?)',(rid,sid,time.time(),json.dumps({'context':context,'snapshot':snapshot}),json.dumps(output),idem,digest))
        return output
    def get(self,rid,sid,token):
        with self.db() as db:
            self.session(db,sid,token)
            row=db.execute('SELECT result FROM runs WHERE id=? AND session_id=?',(rid,sid)).fetchone()
            if not row:raise ApiError(404,'not_found','Không có kết quả trong phiên này.')
        return json.loads(row['result'])
    def history(self,sid,token):
        with self.db() as db:
            self.session(db,sid,token)
            rows=db.execute('SELECT id,created FROM runs WHERE session_id=? ORDER BY created DESC LIMIT 20',(sid,)).fetchall()
        return {'items':[dict(r) for r in rows]}
    def waiting(self,sid,token,payload):
        if payload.get('action') not in ('start','stop'):raise ApiError(422,'invalid_action','action phải là start/stop.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');row=self.session(db,sid,token)
            if payload.get('context_version')!=row['version']:raise ApiError(409,'context_conflict','Ngữ cảnh đã thay đổi.')
            start=(row['waiting'] or time.time()) if payload['action']=='start' else None
            db.execute('UPDATE sessions SET waiting=?,version=version+1 WHERE id=?',(start,sid))
        return {'waiting_started_at':start,'context_version':row['version']+1}
