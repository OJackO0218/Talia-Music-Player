"""
Unit and integration tests for Talia Cloud Relay Server.
Verifies HTTP health probes and real-time multi-peer WebSocket room broadcasting.
"""

import asyncio
import json
import pytest
from aiohttp import web
import websockets

import sys
import os
SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from server import create_app, rooms


def test_cloud_relay_health_and_messaging():
    async def _runner():
        rooms.clear()
        app = create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        port = 9977
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()

        relay_url = f"ws://127.0.0.1:{port}/ws"

        try:
            # Test WebSocket multi-peer room exchange
            async with websockets.connect(relay_url) as ws_host, websockets.connect(relay_url) as ws_guest:
                # 1. Host joins
                await ws_host.send(json.dumps({
                    "type": "join",
                    "room": "PLANET",
                    "name": "HostAlice",
                    "is_host": True,
                }))
                ack_host = json.loads(await asyncio.wait_for(ws_host.recv(), timeout=3.0))
                assert ack_host["type"] == "joined"
                assert ack_host["room"] == "PLANET"
                assert ack_host["is_host"] is True

                # 2. Guest joins
                await ws_guest.send(json.dumps({
                    "type": "join",
                    "room": "PLANET",
                    "name": "GuestBob",
                    "is_host": False,
                }))
                ack_guest = json.loads(await asyncio.wait_for(ws_guest.recv(), timeout=3.0))
                assert ack_guest["type"] == "joined"
                assert "HostAlice" in ack_guest["members"]
                assert "GuestBob" in ack_guest["members"]

                # Host receives peer_joined
                host_notification = json.loads(await asyncio.wait_for(ws_host.recv(), timeout=3.0))
                assert host_notification["type"] == "peer_joined"
                assert host_notification["name"] == "GuestBob"
                assert host_notification["count"] == 2

                # 3. Host broadcasts playback event
                await ws_host.send(json.dumps({
                    "type": "track_change",
                    "title": "Starboy",
                    "artist": "The Weeknd",
                    "timestamp": 12.0,
                    "is_playing": True,
                }))
                guest_track = json.loads(await asyncio.wait_for(ws_guest.recv(), timeout=3.0))
                assert guest_track["type"] == "track_change"
                assert guest_track["title"] == "Starboy"
                assert guest_track["artist"] == "The Weeknd"

        finally:
            await runner.cleanup()

    asyncio.run(_runner())


def test_cloud_relay_host_transfer_and_room_closure():
    async def _runner():
        rooms.clear()
        app = create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        port = 9978
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()

        relay_url = f"ws://127.0.0.1:{port}/ws"

        try:
            # 1. Non-existent room join rejection for listeners
            async with websockets.connect(relay_url) as ws_fake:
                await ws_fake.send(json.dumps({
                    "type": "join",
                    "room": "FAKE99",
                    "name": "LonelyGuest",
                    "is_host": False,
                }))
                err = json.loads(await asyncio.wait_for(ws_fake.recv(), timeout=3.0))
                assert err["type"] == "error"
                assert "does not exist" in err["message"]

            # 2. Host and Guest join valid room
            async with websockets.connect(relay_url) as ws_host, websockets.connect(relay_url) as ws_guest:
                await ws_host.send(json.dumps({
                    "type": "join",
                    "room": "PARTY1",
                    "name": "HostAlice",
                    "is_host": True,
                }))
                ack_h = json.loads(await asyncio.wait_for(ws_host.recv(), timeout=3.0))
                assert ack_h["type"] == "joined"

                await ws_guest.send(json.dumps({
                    "type": "join",
                    "room": "PARTY1",
                    "name": "GuestBob",
                    "is_host": False,
                }))
                ack_g = json.loads(await asyncio.wait_for(ws_guest.recv(), timeout=3.0))
                assert ack_g["type"] == "joined"
                await ws_host.recv()  # peer_joined

                # 3. Host transfers role to GuestBob
                await ws_host.send(json.dumps({
                    "type": "transfer_host",
                    "target": "GuestBob",
                }))

                t_h = json.loads(await asyncio.wait_for(ws_host.recv(), timeout=3.0))
                t_g = json.loads(await asyncio.wait_for(ws_guest.recv(), timeout=3.0))
                assert t_h["type"] == "host_transferred"
                assert t_h["new_host"] == "GuestBob"
                assert t_h["old_host"] == "HostAlice"
                assert t_g["type"] == "host_transferred"
                assert t_g["new_host"] == "GuestBob"

            # 4. Host leaves without transferring -> room closes
            async with websockets.connect(relay_url) as ws_h2, websockets.connect(relay_url) as ws_g2:
                await ws_h2.send(json.dumps({
                    "type": "join",
                    "room": "CLOSE1",
                    "name": "HostDan",
                    "is_host": True,
                }))
                await ws_h2.recv()

                await ws_g2.send(json.dumps({
                    "type": "join",
                    "room": "CLOSE1",
                    "name": "GuestEve",
                    "is_host": False,
                }))
                await ws_g2.recv()
                await ws_h2.recv()  # peer_joined

                # Host leaves
                await ws_h2.close()

                # GuestEve must receive room_closed message
                closed_msg = json.loads(await asyncio.wait_for(ws_g2.recv(), timeout=3.0))
                assert closed_msg["type"] == "room_closed"
                assert "Host has left" in closed_msg["reason"]

        finally:
            await runner.cleanup()

    asyncio.run(_runner())
