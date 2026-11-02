# Talia Listen Together — Free Cloud Relay Server

This is the lightweight WebSocket cloud relay server for **Talia Desktop Music Player**.
It enables friends anywhere in the world to synchronize music playback, karaoke lyrics, and Talia character reactions using only a **5-character Room Code** — with zero VPNs, zero Hamachi, and zero router port forwarding.

---

## 60-Second Free Deployment on Render.com (100% Free Forever)

### Step 1: Open Render
1. Go to [dashboard.render.com](https://dashboard.render.com/) and sign in with your GitHub account.

### Step 2: Create Web Service
1. Click **New +** -> **Web Service**.
2. Select your repository: **`OJackO0218/Talia-Music-Player`**.
3. Configure the fields:
   - **Name**: `talia-party-relay` (or any name you like)
   - **Region**: Any region close to you (e.g. Oregon, Frankfurt, Singapore)
   - **Branch**: `main`
   - **Root Directory**: `server`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python server.py`
   - **Instance Type**: **Free** ($0/month)
4. Click **Deploy Web Service**.

### Step 3: Get Your Permanent Relay URL
Once deployed (takes ~30-45 seconds), Render gives you a secure URL at the top of your dashboard:
`https://talia-party-relay.onrender.com`

Your WebSocket relay address is:
`wss://talia-party-relay.onrender.com`

---

## Using in Talia

In Talia's **Listen Together** window:
- In the **Relay URL** box, paste: `wss://talia-party-relay.onrender.com`
- Host a room: click **Start Hosting Session** and send the 5-character room code to your friend.
- Your friend opens Talia, enters `wss://talia-party-relay.onrender.com` as the Relay URL, types your room code, and clicks **Join Party**.
- **You are now synced globally from anywhere in the world!**
