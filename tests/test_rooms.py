import asyncio
import time

import pytest

from poker.rooms import Room, RoomManager


class FakeWriter:
    def __init__(self):
        self.messages = []
        self.drained = False

    def write(self, message):
        self.messages.append(message)

    async def drain(self):
        self.drained = True


class FakeSession:
    def __init__(self, username):
        self._stdout = FakeWriter()
        self._username = username


def test_room_methods():
    pm = object()
    session_map = {}
    now = time.time()
    room = Room(
        code="1234-alpha",
        name="Alpha",
        created_at=now,
        expires_at=now - 10,
        creator="alice",
        pm=pm,
        session_map=session_map,
        game_in_progress=False,
        is_private=True,
    )

    assert room.is_expired() is True
    room.extend_expiry(minutes=1)
    assert room.is_expired() is False
    remaining = room.time_remaining()
    assert remaining <= 1

    session = FakeSession("alice")
    room.session_map[session] = None
    assert room.can_view_code("alice") is True
    assert room.can_view_code("bob") is False
    room.is_private = False
    assert room.can_view_code("bob") is True


@pytest.mark.asyncio
async def test_room_manager_operations(monkeypatch):
    cleanup_calls = {"count": 0}

    async def fake_cleanup(self):
        cleanup_calls["count"] += 1
        await asyncio.sleep(0)

    monkeypatch.setattr(RoomManager, "_cleanup_expired_rooms", fake_cleanup)

    manager = RoomManager()
    assert "default" in manager.rooms

    room = manager.create_room("alice", name="Alice's Room", is_private=False)
    assert room.code in manager.rooms
    await asyncio.sleep(0)
    assert cleanup_calls["count"] >= 1

    retrieved = manager.get_room(room.code)
    assert retrieved is room

    room.expires_at = time.time() - 5
    assert manager.get_room(room.code) is None

    room = manager.create_room("bob", is_private=True)
    session = FakeSession("bob")
    room.session_map[session] = None
    assert manager.get_room_code_for_user(room.code, "bob") == room.code

    listing = manager.list_rooms_for_user("bob")
    assert any(entry["room"].code == room.code for entry in listing)

    deleted = manager.delete_room(room.code, requester="bob")
    assert deleted is True
    assert room.code not in manager.rooms
    await asyncio.sleep(0)
    assert session._stdout.messages  # notification sent

    deleted_default = manager.delete_room("default", requester="system")
    assert deleted_default is False


@pytest.mark.asyncio
async def test_cleanup_expired_rooms(monkeypatch):
    manager = RoomManager()
    session = FakeSession("guest1")
    room = manager.create_room("guest", is_private=False)
    room.session_map[session] = None
    room.expires_at = time.time() - 1

    sleep_calls = {"count": 0}

    async def fake_sleep(seconds):
        sleep_calls["count"] += 1
        raise asyncio.CancelledError

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    await manager._cleanup_expired_rooms()
    assert sleep_calls["count"] == 1
    assert room.code not in manager.rooms
    assert session._stdout.messages