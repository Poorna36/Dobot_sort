# Factory Dashboard Website Documentation
## SCADA/MOM Industrial Monitoring Interface

This document specifies the design, architecture, and deployment instructions for the factory sorting dashboard website. The web application provides operators with real-time telemetry, sorting statistics, camera capture frames, sorting queue positions, and system status logs.

---

## 1. User Interface Design & Aesthetics

The interface is styled as a premium modern industrial control dashboard (SCADA - Supervisory Control and Data Acquisition).

### 1.1 Visual Tokens
- **Theme:** Sleek dark mode (background `#0B0F19`) to reduce operator eye fatigue.
- **Styling Paradigm:** Glassmorphism using semi-transparent containers with frosted borders and backdrop blur filters.
- **Typography:** Modern tech sans-serif (Google Fonts: `Outfit` or `Inter`).
- **Color System:**
  - **Base Background:** `#0B0F19` (Deep Obsidian Blue)
  - **Component Container:** HSL transparent glass (`hsla(220, 20%, 10%, 0.6)`)
  - **Accent Colors (Status & Color Classes):**
    - **System Status (Active/Ready):** Emerald Green (`#10B981`)
    - **Green Cube:** Lime Emerald (`#10B981`)
    - **Blue Cube:** Saturated Cobalt (`#2563EB`)
    - **Yellow Cube:** Amber Gold (`#D97706`)
    - **Red Cube:** Crimson Red (`#DC2626`)
    - **Unknown Class:** Dark Slate Gray (`#6B7280`)

---

## 2. Layout Structure

The interface uses a fully responsive CSS Grid layout with three main widgets:

```
┌────────────────────────────────────────────────────────┐
│  HEADER: Factory Sorting Station Telemetry  [STATUS]   │
├──────────────────────────┬─────────────────────────────┤
│                          │  WIDGET 2: STATS SUMMARY    │
│  WIDGET 1: LIVE SCAN     │  [G: 12]  [B: 8]  [Y: 4]    │
│            [Webcam ROI]  │  [R: 15]  [U: 2]            │
│  ├────────────────────┤  ├─────────────────────────────┤
│  │ Bounding Box Overlay│  │  WIDGET 3: FIFO QUEUE       │
│  │ [Color classified] │  │  [RED] ◄ [BLUE] ◄ [YELLOW]  │
│  └────────────────────┘  ├─────────────────────────────┤
│  Last Pred: GREEN (98%)  │  WIDGET 4: EVENT LOG        │
│                          │  [12:05:31] IR1: Green Cap  │
└──────────────────────────┴─────────────────────────────┘
```

1. **Header Bar:** Displays the system title, local time, ESP32 serial connectivity status, and a pulsing status indicator (green = sorting running, amber = halted/reject arm active).
2. **Live Scan feed:** Simulates a camera capture window. Shows the raw webcam stream (represented dynamically by high-resolution mock SVGs in the frontend) overlaid with a glowing green bounding box, bounding coordinates, and classification labels.
3. **Telemetry & Stats Panels:**
   - **Sorting Counters:** Displays quantitative stats per color and total sorting count. Uses color-coded progress bars.
   - **FIFO Queue Visualizer:** Displays a horizontal conveyor-like queue showing the order of cubes waiting to be sorted. Items slide and fade out when dequeued.
   - **Event Logger:** Displays a timestamped scrolling terminal log showing physical triggers (e.g. `[14:32:01] IR1 Triggered - Centering Delay Started`).

---

## 3. Communication & Integration Protocol

In a production environment, the Python backend runs a lightweight WebSocket server (using the `websockets` library) which broadcasts events to all connected dashboard pages.

### 3.1 Message Formats (WebSockets)

#### A. Connection Handshake (Payload sent on WS init)
```json
{
  "event": "init",
  "status": "active",
  "port_esp32": "COM3",
  "port_dobot": "COM4",
  "counts": { "green": 12, "blue": 8, "yellow": 4, "red": 15, "unknown": 2 }
}
```

#### B. Cube Classified Event (Sent on IR1 capture completion)
```json
{
  "event": "classified",
  "color": "green",
  "confidence": 0.943,
  "model": "KNN",
  "bbox": [145, 120, 280, 275],
  "queue": ["green", "blue", "yellow"]
}
```

#### C. Cube Sorted Event (Sent when IR2 or IR3 pushes)
```json
{
  "event": "sorted",
  "color": "green",
  "counts": { "green": 13, "blue": 8, "yellow": 4, "red": 15, "unknown": 2 },
  "queue": ["blue", "yellow"]
}
```

#### D. System Halted Event (Sent during Dobot Reject Arm sequence)
```json
{
  "event": "halt",
  "reason": "unknown_object_detected"
}
```

---

## 4. Frontend Simulation Mode

To allow testing and demo validation without connecting the physical Dobot or webcam, `app.js` runs a full **Local Simulation Mode** when a WebSocket connection is unavailable.
- Generates mock sorting events (random color cubes sliding down the conveyor).
- Simulates camera capture overlays with actual coordinates.
- Dynamically increments HTML counter elements, slides items out of the UI queue container, and writes logs.

---

## 5. Deployment Instructions

### 5.1 Simple Local Run
1. Open the [index.html](file:///c:/Workspace/code/projects/dobot_sort/dashboard/index.html) file directly in any modern browser (Chrome, Firefox, Edge, Safari). No server required.
2. The simulation will start automatically.

### 5.2 Python Backend Integration (Production)
1. Add the python dependency `websockets` to `requirements.txt`.
2. In `main.py`, run a WebSocket server in a separate background thread:
   ```python
   import asyncio
   import websockets
   import json

   clients = set()

   async def ws_handler(websocket, path):
       clients.add(websocket)
       # Send initial state
       await websocket.send(json.dumps({
           "event": "init",
           "status": "active",
           "counts": current_counts,
           "queue": list(color_queue)
       }))
       try:
           async for message in websocket:
               pass
       finally:
           clients.remove(websocket)

   def broadcast(data):
       if clients:
           loop = asyncio.new_event_loop()
           asyncio.set_event_loop(loop)
           loop.run_until_complete(
               asyncio.gather(*[client.send(json.dumps(data)) for client in clients])
           )
   ```
3. Update `app.js` websocket URL config to match your local IP (e.g. `ws://localhost:8765`).
