
import http.server
import socketserver

PORT = 8000


class MyRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Hello, world!")

    def log_message(self, format, *args):
        pass  # Disable all logging output


class ThreadingHTTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


with ThreadingHTTPServer(("", PORT), MyRequestHandler) as httpd:
    print(f"Serving on port {PORT}")
    httpd.serve_forever()
