// Deno Deploy WebSocket Relay for Talia Music Player
// Supports multi-region global synchronization via BroadcastChannel

// In-memory room registry for this specific isolate:
// room_code -> Map<WebSocket, { name: string; isHost: boolean }>
const rooms = new Map<string, Map<WebSocket, { name: string; isHost: boolean }>>();

// Known global rooms cache synchronized across all edge nodes:
// room_code -> { hostName: string; lastSeen: number }
const knownRooms = new Map<string, { hostName: string; lastSeen: number }>();

// Cross-isolate communication channel across Deno Deploy's global edge network
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
      } else if (data.type === "host_transferred_announce") {
        if (rooms.has(room)) {
          const roomMap = rooms.get(room)!;
          const msgStr = JSON.stringify({
            type: "host_transferred",
            new_host: data.new_host,
            old_host: data.old_host,
          });
          for (const [peerSocket, peerInfo] of roomMap.entries()) {
            if (peerInfo.name === data.new_host) {
              peerInfo.isHost = true;
            } else if (peerInfo.name === data.old_host) {
              peerInfo.isHost = false;
            }
            if (peerSocket.readyState === WebSocket.OPEN) {
              peerSocket.send(msgStr);
            }
          }
        }
        knownRooms.set(room, { hostName: data.new_host, lastSeen: Date.now() });
      } else if (data.type === "query_room") {
        // Another edge node is querying if this room exists
        if (rooms.has(room) && rooms.get(room)!.size > 0) {
          let hostName = "Host";
          for (const info of rooms.get(room)!.values()) {
            if (info.isHost) {
              hostName = info.name;
              break;
            }
          }
          globalChannel?.postMessage({
            type: "room_announce",
            room: room,
            hostName: hostName,
          });
        }
      } else if (data.type === "broadcast_event") {
        // Playback / seek / track event from another region
        if (rooms.has(room)) {
          const roomMap = rooms.get(room)!;
          const msgStr = JSON.stringify(data.payload);
          for (const [peerSocket, peerInfo] of roomMap.entries()) {
            if (peerSocket.readyState === WebSocket.OPEN && peerInfo.name !== data.sender) {
              peerSocket.send(msgStr);
            }
          }
        }
      } else if (data.type === "peer_joined_announce") {
        if (rooms.has(room)) {
          const roomMap = rooms.get(room)!;
          const msgStr = JSON.stringify({
            type: "peer_joined",
            name: data.name,
            count: data.count,
          });
          for (const [peerSocket] of roomMap.entries()) {
            if (peerSocket.readyState === WebSocket.OPEN) {
              peerSocket.send(msgStr);
            }
          }
        }
      } else if (data.type === "peer_left_announce") {
        if (rooms.has(room)) {
          const roomMap = rooms.get(room)!;
          const msgStr = JSON.stringify({
            type: "peer_left",
            name: data.name,
            count: data.count,
          });
          for (const [peerSocket] of roomMap.entries()) {
            if (peerSocket.readyState === WebSocket.OPEN) {
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

Deno.serve((req) => {
  const upgrade = req.headers.get("upgrade") || "";
  if (upgrade.toLowerCase() !== "websocket") {
    // Health check endpoint for browsers and monitoring
    let totalListeners = 0;
    for (const members of rooms.values()) {
      totalListeners += members.size;
    }
    return new Response(
      JSON.stringify({
        status: "online",
        service: "Talia Listen Together Cloud Relay",
        active_local_rooms: rooms.size,
        active_global_rooms: knownRooms.size,
        total_local_listeners: totalListeners,
      }),
      {
        headers: { "content-type": "application/json" },
      }
    );
  }

  const { socket, response } = Deno.upgradeWebSocket(req);

  let currentRoom = "";
  let peerName = "Listener";
  let isHost = false;

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

        // Validate room existence for listeners (prevent phantom room creation)
        if (!isHost) {
          let roomFound = rooms.has(currentRoom) && rooms.get(currentRoom)!.size > 0;
          const cached = knownRooms.get(currentRoom);
          if (!roomFound && cached && Date.now() - cached.lastSeen < 60000) {
            roomFound = true;
          }

          if (!roomFound && globalChannel) {
            globalChannel.postMessage({ type: "query_room", room: currentRoom });
            await new Promise((resolve) => setTimeout(resolve, 350));
            roomFound = rooms.has(currentRoom) && rooms.get(currentRoom)!.size > 0;
            const postCached = knownRooms.get(currentRoom);
            if (!roomFound && postCached && Date.now() - postCached.lastSeen < 60000) {
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
        }

        if (!rooms.has(currentRoom)) {
          rooms.set(currentRoom, new Map());
        }

        const roomMap = rooms.get(currentRoom)!;
        roomMap.set(socket, { name: peerName, isHost });

        const members = Array.from(roomMap.values()).map((p) => p.name);

        // Acknowledge join to the sender
        socket.send(
          JSON.stringify({
            type: "joined",
            room: currentRoom,
            is_host: isHost,
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

        // Notify other edge regions
        globalChannel?.postMessage({
          type: "peer_joined_announce",
          room: currentRoom,
          name: peerName,
          count: members.length,
        });
      } else if (mtype === "transfer_host" && currentRoom && isHost) {
        const targetName = String(data.target || "").trim();
        if (rooms.has(currentRoom)) {
          const roomMap = rooms.get(currentRoom)!;
          let targetSocket: WebSocket | null = null;
          for (const [s, info] of roomMap.entries()) {
            if (info.name === targetName) {
              targetSocket = s;
              break;
            }
          }
          if (targetSocket) {
            isHost = false;
            roomMap.set(socket, { name: peerName, isHost: false });
            roomMap.set(targetSocket, { name: targetName, isHost: true });
            knownRooms.set(currentRoom, { hostName: targetName, lastSeen: Date.now() });

            const transferMsg = JSON.stringify({
              type: "host_transferred",
              new_host: targetName,
              old_host: peerName,
            });
            for (const [peerSocket] of roomMap.entries()) {
              if (peerSocket.readyState === WebSocket.OPEN) {
                peerSocket.send(transferMsg);
              }
            }
            globalChannel?.postMessage({
              type: "host_transferred_announce",
              room: currentRoom,
              new_host: targetName,
              old_host: peerName,
            });
          }
        }
      } else if (mtype === "leave") {
        socket.close();
      } else if (currentRoom && (rooms.has(currentRoom) || knownRooms.has(currentRoom))) {
        // Broadcast playback / sync events to all peers in the room
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

        // Relay globally across all edge nodes
        globalChannel?.postMessage({
          type: "broadcast_event",
          room: currentRoom,
          sender: peerName,
          payload: data,
        });

        if (isHost) {
          knownRooms.set(currentRoom, { hostName: peerName, lastSeen: Date.now() });
        }
      }
    } catch (err) {
      console.error("Message error:", err);
    }
  };

  socket.onclose = () => {
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
          globalChannel?.postMessage({ type: "room_closed", room: currentRoom });
        }
      }

      globalChannel?.postMessage({
        type: "peer_left_announce",
        room: currentRoom,
        name: peerName,
        count: roomMap.size,
      });
    }
  };

  return response;
});
