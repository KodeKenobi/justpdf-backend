"""
WebSocket Manager for Real-Time Campaign Monitoring
Broadcasts scraper events to connected frontend clients
"""

from flask_sock import Sock
from collections import defaultdict
import json

class WebSocketManager:
    def __init__(self, app=None):
        self.sock = None
        self.connections = defaultdict(list)  # company_id -> [websockets]
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize WebSocket with Flask app"""
        self.sock = Sock(app)
        
        @self.sock.route('/ws/campaign/<int:company_id>')
        def campaign_websocket(ws, company_id):
            """WebSocket endpoint for live campaign monitoring"""
            print(f"WebSocket client connected for company {company_id}")
            
            # Add connection to tracking
            self.connections[company_id].append(ws)
            
            try:
                # Keep connection alive
                while True:
                    # Receive messages from client (if any)
                    data = ws.receive()
                    if data:
                        print(f"Received from client: {data}")
            except Exception as e:
                print(f"WebSocket error for company {company_id}: {e}")
            finally:
                # Remove connection on close
                if ws in self.connections[company_id]:
                    self.connections[company_id].remove(ws)
                print(f"WebSocket client disconnected for company {company_id}")
    
    def broadcast_event(self, company_id: int, event_data: dict):
        """
        Broadcast event to all connected clients for a company
        
        Args:
            company_id: Company ID to broadcast to
            event_data: Dictionary with event details
                - action: str - Action name (e.g., 'visited_homepage')
                - status: str - 'info', 'success', 'warning', 'error'
                - message: str - Human-readable message
                - url: str (optional) - Current page URL
                - screenshot: str (optional) - Screenshot URL/base64
        """
        if company_id not in self.connections or not self.connections[company_id]:
            return
        
        message = json.dumps(event_data)
        
        # Send to all connected clients
        disconnected = []
        for ws in self.connections[company_id]:
            try:
                ws.send(message)
            except Exception as e:
                print(f"Failed to send to WebSocket: {e}")
                disconnected.append(ws)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.connections[company_id].remove(ws)
    
    def close_all(self, company_id: int):
        """Close all connections for a company"""
        if company_id in self.connections:
            for ws in self.connections[company_id]:
                try:
                    ws.close()
                except:
                    pass
            self.connections[company_id].clear()

# Global instance
ws_manager = WebSocketManager()
