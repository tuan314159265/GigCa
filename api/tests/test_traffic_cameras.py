import unittest
from unittest.mock import patch, MagicMock
from email.message import Message

from api.errors import ApiError
from api import traffic_cameras as cams


class TrafficCameraTests(unittest.TestCase):
    def setUp(self):
        cams._cache.clear()
        self.camera={'id':'camera-a','camera_id':'649da72ca6068200171a6dbb','name':'Test',
            'latitude':10.77,'longitude':106.70,'reported_status':'UP','raw':{}}
        self.catalog=({'fetched_at':'2026-10-07T00:00:00Z'},{'camera-a':self.camera})

    def test_nearest_to_segment_interior_not_only_endpoints(self):
        with patch.object(cams,'catalog',return_value=self.catalog):
            value=cams.near_route({'lines':[[[10.77,106.69],[10.77,106.71]]],'radius_m':50})
        self.assertEqual(value['cameras'][0]['distance_to_route_m'],0)
        self.assertEqual(value['cameras'][0]['image_status'],'unchecked')
        self.assertIsNone(value['captured_at'])

    def test_separate_segments_never_join_across_gap(self):
        with patch.object(cams,'catalog',return_value=self.catalog):
            value=cams.near_route({'lines':[[[10.77,106.68],[10.77,106.69]],[[10.77,106.71],[10.77,106.72]]],'radius_m':50})
        self.assertEqual(value['cameras'],[])

    def test_offline_camera_not_claimed_active(self):
        with patch.object(cams,'catalog',return_value=({}, {'camera-a':{**self.camera,'reported_status':'DOWN'}})):
            self.assertEqual(cams.near_route({'lines':[[[10.77,106.7]]]} )['cameras'],[])

    def test_invalid_payloads_rejected(self):
        for payload in ({'lines':[]},{'lines':[[[91,106]]]}, {'lines':[[[10,106]]],'radius_m':float('nan')},
                        {'lines':[[[True,106]]]}, {'lines':[[[10,106]]],'radius_m':1001}):
            with self.subTest(payload=payload),self.assertRaises(ApiError):
                cams.near_route(payload)

    def test_fixed_public_hosts_only(self):
        self.assertTrue(cams.allowed_image_url('https://giaothong.hochiminhcity.gov.vn/Render/ImageHandler.ashx?id=test'))
        for url in ('http://127.0.0.1/image','https://example.com/Render/ImageHandler.ashx',
                    'https://giaothong.hochiminhcity.gov.vn:bad/Render/ImageHandler.ashx',
                    'https://user:secret@giaothong.hochiminhcity.gov.vn/Render/ImageHandler.ashx'):
            self.assertFalse(cams.allowed_image_url(url))

    def test_modern_handler_and_short_cache(self):
        with patch.object(cams,'catalog',return_value=self.catalog),patch.object(cams,'download_image',return_value=(b'jpeg','image/jpeg')) as download:
            first=cams.camera_image('camera-a')
            second=cams.camera_image('camera-a')
        self.assertEqual(first,second)
        download.assert_called_once()
        self.assertIn('/Render/ImageHandler.ashx?id=649da72ca6068200171a6dbb',download.call_args.args[0])

    def test_image_failure_negative_cache_and_unknown_id(self):
        with patch.object(cams,'catalog',return_value=self.catalog),patch.object(cams,'download_image',side_effect=RuntimeError('403')) as download:
            with self.assertRaises(ApiError):cams.camera_image('unknown')
            with self.assertRaises(ApiError):cams.camera_image('camera-a')
            count=download.call_count
            with self.assertRaises(ApiError):cams.camera_image('camera-a')
            self.assertEqual(count,download.call_count)

    def test_html_and_false_jpeg_are_rejected(self):
        for kind,body in [('text/html',b'<html>login'),('image/jpeg',b'<html>error')]:
            response=MagicMock()
            response.__enter__.return_value=response
            headers=Message(); headers['Content-Type']=kind
            response.headers=headers
            response.read.return_value=body
            opener=MagicMock();opener.open.return_value=response
            with patch.object(cams,'build_opener',return_value=opener),self.assertRaises(RuntimeError):
                cams.download_image('https://giaothong.hochiminhcity.gov.vn/Render/ImageHandler.ashx?id=test')

    def test_authenticated_http_binary_image_and_nearest_api(self):
        import json
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from api.v1_server import Handler
        class Auth:
            def me(self,token):
                if token!='test-token':raise ApiError(401,'unauthorized','Login required')
                return {}
        handler=type('CameraTestHandler',(Handler,),{'backend':Auth()})
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        root=f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.object(cams,'catalog',return_value=self.catalog),patch.object(cams,'download_image',return_value=(b'\xff\xd8\xfftest','image/jpeg')):
                with self.assertRaises(HTTPError) as error:
                    urlopen(root+'/api/v1/cameras/camera-a/image')
                self.assertEqual(error.exception.code,401)
                req=Request(root+'/api/v1/cameras/camera-a/image',headers={'Authorization':'Bearer test-token'})
                with urlopen(req) as response:
                    self.assertEqual(response.headers['Content-Type'],'image/jpeg')
                    self.assertTrue(response.headers['X-Camera-Fetched-At'])
                    self.assertEqual(response.read(),b'\xff\xd8\xfftest')
                req=Request(root+'/api/v1/cameras/near-route',data=json.dumps({'lines':[[[10.77,106.7]]]}).encode(),
                    headers={'Authorization':'Bearer test-token','Content-Type':'application/json'})
                with urlopen(req) as response:
                    self.assertEqual(json.load(response)['cameras'][0]['id'],'camera-a')
        finally:
            server.shutdown();server.server_close()
