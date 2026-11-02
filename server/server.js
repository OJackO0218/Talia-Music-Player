// Talia Listen Together - Ultra-Lightweight WebSocket Cloud Relay
// Works 100% free on Glitch.com with ZERO credit card.

const http = require('http');
const WebSocket = require('ws');

// In-memory room registry: room_code -> Map(ws => { name, is_host })
const rooms = {};

const server = http.createServer((req, res) => {
  res.writeHead(200, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*'
  });

  const activeRooms = Object.keys(rooms).length;
  let totalListeners = 0;
  for (const r in rooms) {
    totalListeners += rooms[r].size;
  }

  res.end(JSON.stringify({
    status: 'online',
    service: 'Talia Listen Together Cloud Relay',
    active_rooms: activeRooms,
    total_listeners: totalListeners
  }, null, 2));
});

const wss = new WebSocket.Server({ server });

wss.on('connection', (ws) => {
  let currentRoom = null;
  let peerName = 'Listener';
  let isHost = false;

  ws.on('message', (raw) => {
    try {
      const data = JSON.parse(raw);
      const mtype = data.type;

      // 1. Join room
      if (mtype === 'join') {
        const r = String(data.room || '').trim().toUpperCase();
        if (!r) return;

        currentRoom = r;
        peerName = String(data.name || 'Listener').trim() || 'Listener';
        isHost = Boolean(data.is_host);

        if (!rooms[r]) {
          rooms[r] = new Map();
        }
        rooms[r].set(ws, { name: peerName, is_host: isHost });

        const members = Array.from(rooms[r].values()).map(p => p.name);
        console.log(`[JOIN] ${peerName} joined room ${r} (total: ${members.length})`);

        // Send confirmation back to this peer
        ws.send(JSON.stringify({
          type: 'joined',
          room: r,
          is_host: isHost,
          members: members,
          count: members.length
        }));

        // Broadcast peer_joined to all other peers in the room
        const peerJoinedMsg = JSON.stringify({
          type: 'peer_joined',
          name: peerName,
          is_host: isHost,
          count: members.length
        });

        for (const [client] of rooms[r]) {
          if (client !== ws && client.readyState === WebSocket.OPEN) {
            client.send(peerJoinedMsg);
          }
        }
      }
      // 2. Leave room
      else if (mtype === 'leave') {
        ws.close();
      }
      // 3. Broadcast events (track_change, play, pause, seek, heartbeat, reaction)
      else if (currentRoom && rooms[currentRoom]) {
        data.sender = peerName;
        const broadcastMsg = JSON.stringify(data);
        for (const [client] of rooms[currentRoom]) {
          if (client !== ws && client.readyState === WebSocket.OPEN) {
            client.send(broadcastMsg);
          }
        }
      }
    } catch (err) {
      console.error('Error processing party message:', err);
    }
  });

  ws.on('close', () => {
    if (currentRoom && rooms[currentRoom]) {
      rooms[currentRoom].delete(ws);
      const remaining = Array.from(rooms[currentRoom].values()).map(p => p.name);
      if (remaining.length > 0) {
        console.log(`[LEAVE] ${peerName} left room ${currentRoom} (${remaining.length} remaining)`);
        const peerLeftMsg = JSON.stringify({
          type: 'peer_left',
          name: peerName,
          count: remaining.length
        });
        for (const [client] of rooms[currentRoom]) {
          if (client.readyState === WebSocket.OPEN) {
            client.send(peerLeftMsg);
          }
        }
      } else {
        delete rooms[currentRoom];
        console.log(`[ROOM CLOSED] Room ${currentRoom} is now empty.`);
      }
    }
  });

  ws.on('error', (err) => {
    console.error('WebSocket connection error:', err);
  });
});

const port = process.env.PORT || 3000;
server.listen(port, () => {
  console.log(`Talia Cloud Relay active on port ${port}`);
});
