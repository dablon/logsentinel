"""Mock LLM server for testing"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread


class MockLLMHandler(BaseHTTPRequestHandler):
    """Handler for mock LLM API"""
    
    responses = {
        "/v1/chat/completions": {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Mock analysis: Found 2 errors and 1 warning in logs."
                }
            }]
        }
    }
    
    def do_POST(self):
        """Handle POST request"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        # Return mock response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        response = json.dumps(self.responses.get(self.path, {}))
        self.wfile.write(response.encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logging


def start_mock_server(port=8000):
    """Start mock LLM server"""
    server = HTTPServer(('localhost', port), MockLLMHandler)
    thread = Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server


def stop_mock_server(server):
    """Stop mock LLM server"""
    server.shutdown()
