"""
WebSocket Manager for Real-Time Campaign Monitoring
Broadcasts scraper events to connected frontend clients
"""

from flask_sock import Sock
from collections import defaultdict
import json
import threading
import queue
import time

class WebSocketManager:
    def __init__(self, app=None):
        self.sock = None
        self.connections = defaultdict(list)  # company_id -> [websockets]
        self._lock = threading.Lock()
        self._event_queue = queue.Queue(maxsize=2000)
        self._worker_thread = None
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize WebSocket with Flask app"""
        self.sock = Sock(app)
        
        # Start background worker thread if not already running
        if not self._worker_thread or not self._worker_thread.is_alive():
            self._worker_thread = threading.Thread(target=self._broadcast_worker, daemon=True)
            self._worker_thread.start()
            print("[WebSocket] Background worker thread started.")

        @self.sock.route('/ws/campaign/<campaign_id>')
        def campaign_websocket(ws, campaign_id):
            """WebSocket endpoint for live campaign monitoring"""
            print(f"WebSocket client connected for campaign {campaign_id}")
            
            # Add connection to tracking (using campaign_id as room)
            with self._lock:
                self.connections[campaign_id].append(ws)
            
            try:
                # Keep connection alive
                while True:
                    # Receive messages from client (if any)
                    data = ws.receive(timeout=30) # Increased timeout
                    if data:
                        print(f"Received from client: {data}")
            except Exception as e:
                # Don't log normal disconnects as errors
                err_str = str(e).lower()
                if 'closed' not in err_str and 'fin must be set' not in err_str:
                    print(f"[WebSocket] Campaign {campaign_id} error: {e}")
                elif 'fin must be set' in err_str:
                    print(f"[WebSocket] Campaign {campaign_id} framing error (FIN must be set): {e}")
            finally:
                # Remove connection on close
                with self._lock:
                    if ws in self.connections[campaign_id]:
                        self.connections[campaign_id].remove(ws)
                print(f"WebSocket client disconnected for campaign {campaign_id}")
    
    def broadcast_event(self, campaign_id: int, event_data: dict):
        """
        Add event to queue for asynchronous broadcasting
        """
        try:
            # We use put_nowait to ensure we NEVER block the caller (especially the campaign loop)
            # If the queue is full (2000 messages), we drop the oldest messages to keep processing alive
            if self._event_queue.full():
                try: self._event_queue.get_nowait()
                except queue.Empty: pass
            
            self._event_queue.put_nowait((campaign_id, event_data))
        except Exception as e:
            print(f"[WebSocket] Error queuing event: {e}")

    def _broadcast_worker(self):
        """Background thread that drains the queue and sends to clients"""
        while True:
            try:
                campaign_id, event_data = self._event_queue.get()
                
                with self._lock:
                    clients = list(self.connections.get(campaign_id, []))
                
                if clients:
                    message = json.dumps(event_data)
                    disconnected = []
                    
                    for ws in clients:
                        try:
                            # Still blocks slightly per client, but in its own thread
                            ws.send(message)
                        except Exception as e:
                            # Silent fail for individual clients, add to disconnect list
                            if 'fin must be set' in str(e).lower():
                                print(f"[WebSocket] Framing error during broadcast: {e}")
                            disconnected.append(ws)
                    
                    if disconnected:
                        with self._lock:
                            for ws in disconnected:
                                if ws in self.connections[campaign_id]:
                                    self.connections[campaign_id].remove(ws)
                
                self._event_queue.task_done()
            except Exception as worker_err:
                print(f"[WebSocket] Worker error: {worker_err}")
                time.sleep(1) # Prevent tight loop on error
    
    def close_all(self, campaign_id: int):
        """Close all connections for a campaign"""
        if campaign_id in self.connections:
            for ws in self.connections[campaign_id]:
                try:
                    ws.close()
                except:
                    pass
            self.connections[campaign_id].clear()

# Global instance
ws_manager = WebSocketManager()
