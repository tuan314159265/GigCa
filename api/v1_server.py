"""Run: python -m api.v1_server. Existing dashboard routes remain compatible."""
import json
import re
import uuid
import os
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from api.dashboard import DashboardHandler, load_local_settings
from api.session_service import Backend, ApiError

class Handler(DashboardHandler):
    backend = None
    def dispatch(self,method):
        path=urlsplit(self.path).path
        if not path.startswith('/api/v1/'):
            return False
        request_id=str(uuid.uuid4())
        try:
            payload={}
            if method in ('POST','PATCH'):
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=16384:raise ValueError()
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict):raise ValueError()
                except (ValueError,UnicodeError):raise ApiError(422,'invalid_json','JSON không hợp lệ.')
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            service=self.backend
            if path=='/api/v1/sessions' and method=='POST':result=service.create()
            elif (m:=re.fullmatch('/api/v1/sessions/([^/]+)/(context|waiting|recommendations)',path)):
                sid,action=m.groups()
                if action=='context' and method=='PATCH':result=service.update(sid,token,payload)
                elif action=='waiting' and method=='POST':result=service.waiting(sid,token,payload)
                elif action=='recommendations' and method=='GET':result=service.history(sid,token)
                else:raise ApiError(404,'not_found','Endpoint không tồn tại.')
            elif path=='/api/v1/recommendations' and method=='POST':
                result=service.run(payload.get('session_id'),token,payload,self.headers.get('Idempotency-Key'))
            elif (m:=re.fullmatch('/api/v1/recommendations/([^/]+)',path)) and method=='GET':
                sid=parse_qs(urlsplit(self.path).query).get('session_id',[''])[0]
                result=service.get(m[1],sid,token)
            else:raise ApiError(404,'not_found','Endpoint không tồn tại.')
            self.send_json(result,201 if method=='POST' and path=='/api/v1/sessions' else 200)
        except ApiError as exc:
            self.send_json({'error':{'code':exc.code,'message':str(exc),'request_id':request_id,'retryable':False}},exc.status)
        except RuntimeError:
            self.send_json({'error':{'code':'source_unavailable','message':'Nguồn dữ liệu chưa sẵn sàng.','request_id':request_id,'retryable':True}},503)
        except Exception:
            self.send_json({'error':{'code':'internal_error','message':'Không xử lý được yêu cầu.','request_id':request_id,'retryable':True}},500)
        return True
    def do_GET(self):
        if not self.dispatch('GET'):super().do_GET()
    def do_POST(self):
        if not self.dispatch('POST'):super().do_POST()
    def do_PATCH(self):
        if not self.dispatch('PATCH'):self.send_error(404)

if __name__=='__main__':
    load_local_settings()
    Handler.backend=Backend()
    host=os.environ.get('GIGCA_API_HOST','127.0.0.1')
    port=int(os.environ.get('GIGCA_API_PORT','8000'))
    print(f'GigCa API v1: http://{host}:{port}',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
