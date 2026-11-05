// Deno Deploy WebSocket Relay for Talia Music Player
// Supports multi-region global synchronization via Deno KV + BroadcastChannel + KV Watch

// In-memory room registry for this specific isolate:
// room_code -> Map<WebSocket, { name: string; isHost: boolean }>
const rooms = new Map<string, Map<WebSocket, { name: string; isHost: boolean }>>();

// Known global rooms cache synchronized across edge nodes:
// room_code -> { hostName: string; lastSeen: number }
const knownRooms = new Map<string, { hostName: string; lastSeen: number }>();

// Cross-isolate communication channel across Deno Deploy's edge network
let globalChannel: BroadcastChannel | null = null;
try {
  globalChannel = new BroadcastChannel("talia_global_party_relay");
  globalChannel.onmessage = (event) => {
    try {
      const data = event.data;
      if (!data || !data.room) return;
      const room = String(data.room).toUpperCase();

      if (data.type === "room_announce") {
        knownRooms.set(room, {
          hostName: data.hostName || "Host",
          lastSeen: Date.now(),
        });
      } else if (data.type === "room_closed") {
        knownRooms.delete(room);
        if (rooms.has(room)) {
          const roomMap = rooms.get(room)!;
          const closeMsg = JSON.stringify({
            type: "room_closed",
            reason: "Host has left the party session. Room closed.",
          });
          for (const [peerSocket] of roomMap.entries()) {
            if (peerSocket.readyState === WebSocket.OPEN) {
              peerSocket.send(closeMsg);
              peerSocket.close();
            }
          }
          rooms.delete(room);
        }
      } else if (data.type === "broadcast_event") {
        if (rooms.has(room)) {
          const roomMap = rooms.get(room)!;
          const msgStr = JSON.stringify(data.payload);
          for (const [peerSocket, peerInfo] of roomMap.entries()) {
            if (peerSocket.readyState === WebSocket.OPEN && peerInfo.name !== data.sender) {
              peerSocket.send(msgStr);
            }
          }
        }
      }
    } catch (err) {
      console.error("Global channel error:", err);
    }
  };
} catch {
  // BroadcastChannel unavailable in local fallback environments
}

// Global persistent room registry using Deno KV (cross-region synchronization)
// deno-lint-ignore no-explicit-any
let kv: any = null;
try {
  // @ts-ignore: Deno.openKv available in Deno runtime
  if (typeof Deno.openKv === "function") {
    // @ts-ignore: Deno.openKv
    kv = await Deno.openKv();
  }
} catch {
  // KV unavailable in offline or restricted environments
}

Deno.serve(async (req) => {
  const upgrade = req.headers.get("upgrade") || "";
  if (upgrade.toLowerCase() !== "websocket") {
    // Global health check: queries Deno KV so ALL regions see active rooms
    const activeRoomsList: { room: string; host: string; age_seconds: number }[] = [];
    if (kv) {
      try {
        const iter = kv.list({ prefix: ["rooms"] });
        for await (const entry of iter) {
          if (entry.key.length > 1 && entry.value) {
            const val = entry.value as { hostName?: string; createdAt?: number };
            activeRoomsList.push({
              room: String(entry.key[1]),
              host: val.hostName || "Host",
              age_seconds: Math.floor((Date.now() - (val.createdAt || Date.now())) / 1000),
            });
          }
        }
      } catch (err) {
        console.error("KV list error:", err);
      }
    }

    let localListeners = 0;
    for (const members of rooms.values()) {
      localListeners += members.size;
    }

    return new Response(
      JSON.stringify(
        {
          status: "online",
          service: "Talia Listen Together Cloud Relay",
          kv_enabled: Boolean(kv),
          active_global_rooms_count: activeRoomsList.length,
          active_global_rooms: activeRoomsList,
          local_isolate_rooms_count: rooms.size,
          local_isolate_listeners: localListeners,
          edge_region: req.headers.get("x-deno-ray") || "auto",
        },
        null,
        2
      ),
      {
        headers: { "content-type": "application/json" },
      }
    );
  }

  const { socket, response } = Deno.upgradeWebSocket(req);

  let currentRoom = "";
  let peerName = "Listener";
  let isHost = false;
  let kvWatcherRunning = false;

  socket.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      const mtype = data.type;

      if (mtype === "join") {
        currentRoom = String(data.room || "").trim().toUpperCase();
        peerName = String(data.name || "Listener").trim();
        isHost = Boolean(data.is_host);

        if (!currentRoom) {
          socket.send(JSON.stringify({ type: "error", message: "Room code required" }));
          socket.close();
          return;
        }

        // Validate room existence for listeners
        if (!isHost) {
          let roomFound = rooms.has(currentRoom) && rooms.get(currentRoom)!.size > 0;
          let cached = knownRooms.get(currentRoom);
          if (!roomFound && cached && Date.now() - cached.lastSeen < 300000) {
            roomFound = true;
          }

          // Check global Deno KV across all regions
          if (!roomFound && kv) {
            try {
              const res = await kv.get(["rooms", currentRoom]);
              if (res && res.value) {
                roomFound = true;
                knownRooms.set(currentRoom, { hostName: res.value.hostName, lastSeen: Date.now() });
              }
            } catch {
              // Ignore KV read error
            }
          }

          // If still not found, query BroadcastChannel
          if (!roomFound && globalChannel) {
            globalChannel.postMessage({ type: "query_room", room: currentRoom });
            await new Promise((resolve) => setTimeout(resolve, 450));
            roomFound = rooms.has(currentRoom) && rooms.get(currentRoom)!.size > 0;
            const postCached = knownRooms.get(currentRoom);
            if (!roomFound && postCached && Date.now() - postCached.lastSeen < 300000) {
              roomFound = true;
            }
          }

          if (!roomFound) {
            socket.send(
              JSON.stringify({
                type: "error",
                message: `Room '${currentRoom}' does not exist or host is offline.`,
              })
            );
            socket.close();
            return;
          }
        }

        // Register room announcement if host
        if (isHost) {
          knownRooms.set(currentRoom, { hostName: peerName, lastSeen: Date.now() });
          globalChannel?.postMessage({
            type: "room_announce",
            room: currentRoom,
            hostName: peerName,
          });
          if (kv) {
            try {
              await kv.set(["rooms", currentRoom], { hostName: peerName, createdAt: Date.now() }, { expireIn: 1000 * 60 * 60 * 4 });
            } catch {
              // Ignore KV write error
            }
          }
        }

        if (!rooms.has(currentRoom)) {
          rooms.set(currentRoom, new Map());
        }

        const roomMap = rooms.get(currentRoom)!;
        roomMap.set(socket, { name: peerName, isHost });

        // Ensure host is always in the member list even across different edge datacenters
        const activeHost = isHost ? peerName : (knownRooms.get(currentRoom)?.hostName || "Host");
        const membersSet = new Set<string>();
        if (!isHost) membersSet.add(activeHost);
        for (const p of roomMap.values()) {
          membersSet.add(p.name);
        }
        const members = Array.from(membersSet);

        // Acknowledge join to the sender
        socket.send(
          JSON.stringify({
            type: "joined",
            room: currentRoom,
            is_host: isHost,
            host_name: activeHost,
            members: members,
            count: members.length,
          })
        );

        // Notify local listeners
        const peerJoinedMsg = JSON.stringify({
          type: "peer_joined",
          name: peerName,
          count: members.length,
        });

        for (const [peerSocket] of roomMap.entries()) {
          if (peerSocket !== socket && peerSocket.readyState === WebSocket.OPEN) {
            peerSocket.send(peerJoinedMsg);
          }
        }

        // Start real-time cross-region KV event listener for this room
        if (kv && !kvWatcherRunning) {
          kvWatcherRunning = true;
          (async () => {
            try {
              const watcher = kv.watch([["room_events", currentRoom]]);
              for await (const [entry] of watcher) {
                if (!kvWatcherRunning) break;
                if (!entry || !entry.value) continue;
                const evt = entry.value as { sender: string; payload: any; ts: number };
                if (evt.sender === peerName) continue;
                if (Date.now() - evt.ts > 10000) continue;
                if (socket.readyState === WebSocket.OPEN) {
                  socket.send(JSON.stringify(evt.payload));
                }
              }
            } catch {
              // KV watch closed
            }
          })();
        }
      } else if (mtype === "leave") {
        socket.close();
      } else if (currentRoom && (rooms.has(currentRoom) || knownRooms.has(currentRoom))) {
        // Broadcast playback / sync events to local peers in this isolate
        data.sender = peerName;
        const msgStr = JSON.stringify(data);

        if (rooms.has(currentRoom)) {
          const roomMap = rooms.get(currentRoom)!;
          for (const [peerSocket] of roomMap.entries()) {
            if (peerSocket !== socket && peerSocket.readyState === WebSocket.OPEN) {
              peerSocket.send(msgStr);
            }
          }
        }

        // Broadcast to isolates in same datacenter via BroadcastChannel
        globalChannel?.postMessage({
          type: "broadcast_event",
          room: currentRoom,
          sender: peerName,
          payload: data,
        });

        // Broadcast globally to all edge datacenters via Deno KV
        if (kv) {
          try {
            await kv.set(
              ["room_events", currentRoom],
              { sender: peerName, payload: data, ts: Date.now() },
              { expireIn: 60000 }
            );
          } catch {
            // Ignore KV event write error
          }
        }

        if (isHost) {
          knownRooms.set(currentRoom, { hostName: peerName, lastSeen: Date.now() });
        }
      }
    } catch (err) {
      console.error("Message error:", err);
    }
  };

  socket.onclose = async () => {
    kvWatcherRunning = false;
    if (currentRoom && rooms.has(currentRoom)) {
      const roomMap = rooms.get(currentRoom)!;
      roomMap.delete(socket);

      if (roomMap.size > 0) {
        let hasHost = false;
        for (const info of roomMap.values()) {
          if (info.isHost) {
            hasHost = true;
            break;
          }
        }

        if (isHost && !hasHost) {
          const closeMsg = JSON.stringify({
            type: "room_closed",
            reason: "Host has left the party session. Room closed.",
          });
          for (const [peerSocket] of roomMap.entries()) {
            if (peerSocket.readyState === WebSocket.OPEN) {
              peerSocket.send(closeMsg);
              peerSocket.close();
            }
          }
          rooms.delete(currentRoom);
          knownRooms.delete(currentRoom);
          if (kv) {
            try {
              await kv.delete(["rooms", currentRoom]);
              await kv.delete(["room_events", currentRoom]);
            } catch {}
          }
          globalChannel?.postMessage({ type: "room_closed", room: currentRoom });
        } else {
          const members = Array.from(roomMap.values()).map((p) => p.name);
          const peerLeftMsg = JSON.stringify({
            type: "peer_left",
            name: peerName,
            is_host: isHost,
            count: members.length,
          });
          for (const [peerSocket] of roomMap.entries()) {
            if (peerSocket.readyState === WebSocket.OPEN) {
              peerSocket.send(peerLeftMsg);
            }
          }
        }
      } else {
        rooms.delete(currentRoom);
        if (isHost) {
          knownRooms.delete(currentRoom);
          if (kv) {
            try {
              await kv.delete(["rooms", currentRoom]);
              await kv.delete(["room_events", currentRoom]);
            } catch {}
          }
          globalChannel?.postMessage({ type: "room_closed", room: currentRoom });
        }
      }
    }
  };

  return response;
});
