"""방(세션) 저장소와 접속 관리.

계정도 DB도 없다. 방은 메모리에 들고 있다가 아무도 없는 채로 일정 시간이
지나면 지운다. 동시 접속 규모가 작으니 이 정도로 충분하다.
"""

from __future__ import annotations

import asyncio
import random
import string
import time
from typing import Any

from . import game

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 헷갈리는 O/0, I/1 제외
CODE_LENGTH = 6
ROOM_TTL_SECONDS = 12 * 60 * 60  # 마지막 활동 후 12시간
SWEEP_INTERVAL = 10 * 60


class RoomError(Exception):
    pass


class Room:
    def __init__(self, code: str) -> None:
        self.code = code
        self.state = game.new_state(code)
        self.lock = asyncio.Lock()
        self.connections: dict[str, set[Any]] = {}  # playerId -> {WebSocket}
        self.last_activity = time.time()

    # -- 접속 --------------------------------------------------------------

    def attach(self, player_id: str, websocket: Any) -> None:
        self.connections.setdefault(player_id, set()).add(websocket)
        player = game.player_by_id(self.state, player_id)
        if player:
            player["connected"] = True
        self.touch()

    def detach(self, player_id: str, websocket: Any) -> None:
        sockets = self.connections.get(player_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                self.connections.pop(player_id, None)
                player = game.player_by_id(self.state, player_id)
                if player:
                    player["connected"] = False
        self.touch()

    def touch(self) -> None:
        self.last_activity = time.time()

    @property
    def is_empty(self) -> bool:
        return not any(self.connections.values())

    # -- 참가 --------------------------------------------------------------

    def join(self, name: str) -> dict[str, Any]:
        player = game.add_player(self.state, name)
        self.touch()
        return {"playerId": player["id"], "token": player["token"], "roomCode": self.code}

    def authenticate(self, player_id: str, token: str) -> dict[str, Any]:
        for player in self.state["players"]:
            if player["id"] == player_id and player["token"] == token:
                return player
        raise RoomError("이 방의 참가자 정보가 아닙니다. 다시 입장해 주세요.")

    def snapshot(self) -> dict[str, Any]:
        return game.public_state(self.state)


class RoomRegistry:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._sweeper: asyncio.Task | None = None

    def _new_code(self) -> str:
        for _ in range(200):
            code = "".join(random.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self._rooms:
                return code
        raise RoomError("방 코드를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.")

    def create(self) -> Room:
        room = Room(self._new_code())
        self._rooms[room.code] = room
        return room

    def get(self, code: str) -> Room:
        room = self._rooms.get((code or "").strip().upper())
        if room is None:
            raise RoomError("그런 방이 없습니다. 코드를 다시 확인해 주세요.")
        return room

    def exists(self, code: str) -> bool:
        return (code or "").strip().upper() in self._rooms

    def sweep(self) -> int:
        now = time.time()
        stale = [
            code
            for code, room in self._rooms.items()
            if room.is_empty and now - room.last_activity > ROOM_TTL_SECONDS
        ]
        for code in stale:
            self._rooms.pop(code, None)
        return len(stale)

    async def start_sweeper(self) -> None:
        async def loop() -> None:
            while True:
                await asyncio.sleep(SWEEP_INTERVAL)
                self.sweep()

        self._sweeper = asyncio.create_task(loop())

    async def stop_sweeper(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
            try:
                await self._sweeper
            except asyncio.CancelledError:
                pass
            self._sweeper = None

    @property
    def count(self) -> int:
        return len(self._rooms)


registry = RoomRegistry()
