"""
WebSocket 연결 관리
"""

from fastapi import WebSocket
from typing import Dict, List
import json


class ConnectionManager:
    """WebSocket 연결 관리 클래스"""
    
    def __init__(self):
        # 활성 연결 저장
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """클라이언트 연결"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        print(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, client_id: str):
        """클라이언트 연결 해제"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            print(f"Client {client_id} disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, client_id: str):
        """특정 클라이언트에게 메시지 전송"""
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)
    
    async def broadcast(self, message: str):
        """모든 연결된 클라이언트에게 브로드캐스트"""
        for client_id, connection in self.active_connections.items():
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"Error broadcasting to {client_id}: {e}")
    
    async def broadcast_to_agents(self, message: str, exclude_client: str | None = None):
        """상담원에게만 브로드캐스트"""
        for client_id, connection in self.active_connections.items():
            if client_id != exclude_client and client_id.startswith("agent_"):
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print(f"Error broadcasting to agent {client_id}: {e}")
    
    async def broadcast_to_all_agents(self, data: dict):
        """모든 상담원에게 JSON 데이터 브로드캐스트"""
        message = json.dumps(data)
        await self.broadcast_to_agents(message)


# 전역 ConnectionManager 인스턴스
manager = ConnectionManager()