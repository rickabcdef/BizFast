# -*- coding: utf-8 -*-
"""SPA fallback static server for BizFast admin-web 验证用（history 路由回退到 index.html）"""
import http.server
import os
import socketserver
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'dist')
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8091
PREFIX = '/admin/'


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path.startswith(PREFIX):
            rel = path[len(PREFIX):]
            if rel and os.path.isfile(os.path.join(ROOT, 'admin', rel)):
                self.path = PREFIX + rel
            else:
                self.path = PREFIX + 'index.html'
        return super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


with socketserver.TCPServer(('127.0.0.1', PORT), Handler) as httpd:
    print(f'serving {ROOT} on http://127.0.0.1:{PORT}{PREFIX}')
    httpd.serve_forever()
