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
        
        @self.sock.route('/ws/campaign/<int:campaign_id>')
        def campaign_websocket(ws, campaign_id):
            """WebSocket endpoint for live campaign monitoring"""
            print(f"WebSocket client connected for campaign {campaign_id}")
            
            # Add connection to tracking (using campaign_id as room)
            self.connections[campaign_id].append(ws)
            
            try:
                # Keep connection alive
                while True:
                    # Receive messages from client (if any)
                    data = ws.receive(timeout=10) # Add timeout to avoid hanging
                    if data:
                        print(f"Received from client: {data}")
            except Exception as e:
                print(f"WebSocket error for campaign {campaign_id}: {e}")
            finally:
                # Remove connection on close
                if ws in self.connections[campaign_id]:
                    self.connections[campaign_id].remove(ws)
                print(f"WebSocket client disconnected for campaign {campaign_id}")
    
    def broadcast_event(self, campaign_id: int, event_data: dict):
        """
        Broadcast event to all connected clients for a campaign
        """
        if campaign_id not in self.connections or not self.connections[campaign_id]:
            return
        
        message = json.dumps(event_data)
        
        # Send to all connected clients
        disconnected = []
        for ws in self.connections[campaign_id]:
            try:
                ws.send(message)
            except Exception as e:
                print(f"Failed to send to WebSocket: {e}")
                disconnected.append(ws)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.connections[campaign_id].remove(ws)
    
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
