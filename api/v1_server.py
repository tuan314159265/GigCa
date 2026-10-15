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
        success_status = 200
        try:
            payload={}
            if method in ('POST','PATCH'):
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    max_size = 1_048_576 if path == '/api/v1/me/log-imports/preview' else 65536 if path == '/api/v1/cameras/near-route' else 16384
                    if not 0<length<=max_size:raise ValueError()
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict):raise ValueError()
                except (ValueError,UnicodeError):raise ApiError(422,'invalid_json','JSON không hợp lệ.')
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            service=self.backend
            query = parse_qs(urlsplit(self.path).query)
            page = {'limit': query.get('limit', ['20'])[0], 'offset': query.get('offset', ['0'])[0]}
            if path=='/api/v1/auth/register' and method=='POST':
                result=service.register(payload,self.client_address[0]);success_status=201
            elif path=='/api/v1/auth/login' and method=='POST':
                result=service.login(payload,self.client_address[0])
            elif path=='/api/v1/auth/logout' and method=='POST':result=service.logout(token)
            elif path=='/api/v1/me' and method=='GET':result=service.me(token)
            elif path=='/api/v1/me/data-status' and method=='GET':result=service.data_status(token)
            elif path=='/api/v1/cameras/near-route' and method=='POST':
                service.me(token)
                from api.traffic_cameras import near_route
                result=near_route(payload)
            elif (m:=re.fullmatch('/api/v1/cameras/([a-zA-Z0-9_-]+)/image',path)) and method=='GET':
                service.me(token)
                from api.traffic_cameras import camera_image
                body,kind,fetched_at=camera_image(m[1])
                self.send_response(200)
                self.send_header('Content-Type',kind)
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','private, max-age=20')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('X-Camera-Fetched-At',fetched_at)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # User switched roads/cameras while the image was loading.
                return True
            elif path=='/api/v1/research/drivers' and method=='GET':
                service.me(token)
                from api.research_demo import catalog
                result=catalog()
            elif path=='/api/v1/research/recommendations' and method=='POST':
                service.me(token)
                from api.research_demo import recommend_demo
                result=recommend_demo(payload)
            elif path=='/api/v1/me/profile' and method in ('GET','PATCH'):
                result=service.profile(token,payload if method=='PATCH' else None)
            elif path in ('/api/v1/me/trips','/api/v1/me/wait-spells') and method=='GET':
                result=service.records(token,'trips' if path.endswith('/trips') else 'waits',**page)
            elif path=='/api/v1/me/log-imports/preview' and method=='POST':
                result=service.preview_import(token,payload);success_status=201
            elif (m:=re.fullmatch('/api/v1/me/log-imports/([^/]+)/confirm',path)) and method=='POST':
                if payload:raise ApiError(422,'invalid_request','Không gửi thêm dữ liệu khi xác nhận.')
                result=service.confirm_import(token,m[1])
            elif path=='/api/v1/me/recommendations' and method=='GET':
                result=service.driver_history(token,**page)
            elif (m:=re.fullmatch('/api/v1/me/recommendations/([^/]+)',path)) and method=='GET':
                result=service.driver_history(token,rid=m[1])
            elif path=='/api/v1/sessions' and method=='POST':
                result=service.create(token or None);success_status=201
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
            self.send_json(result,success_status)
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
