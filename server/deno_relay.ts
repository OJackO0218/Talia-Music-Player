// Deno Deploy WebSocket Relay for Talia Music Player
// In-memory room registry: room_code -> Map<WebSocket, { name, isHost }>
const rooms = new Map<string, Map<WebSocket, { name: string; isHost: boolean }>>();

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
        active_rooms: rooms.size,
        total_listeners: totalListeners,
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

  socket.onmessage = (event) => {
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
          })
        );

        // Notify other listeners in the room
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
      } else if (mtype === "leave") {
        socket.close();
      } else if (currentRoom && rooms.has(currentRoom)) {
        // Broadcast playback / sync events to all peers in the room
        data.sender = peerName;
        const msgStr = JSON.stringify(data);
        const roomMap = rooms.get(currentRoom)!;
        for (const [peerSocket] of roomMap.entries()) {
          if (peerSocket !== socket && peerSocket.readyState === WebSocket.OPEN) {
            peerSocket.send(msgStr);
          }
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
        const members = Array.from(roomMap.values()).map((p) => p.name);
        const peerLeftMsg = JSON.stringify({
          type: "peer_left",
          name: peerName,
          count: members.length,
        });
        for (const [peerSocket] of roomMap.entries()) {
          if (peerSocket.readyState === WebSocket.OPEN) {
            peerSocket.send(peerLeftMsg);
          }
        }
      } else {
        rooms.delete(currentRoom);
      }
    }
  };

  return response;
});
