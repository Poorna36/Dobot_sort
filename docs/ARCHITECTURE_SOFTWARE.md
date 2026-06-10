# Software Architecture & Pipeline
## Dobot Color Sorting System

---

## Overview

All software runs on the laptop. The system is a single Python process with multiple threads handling concurrent operations: serial communication with ESP32, image capture and classification, Dobot belt/arm control, and an optional live dashboard.

---

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.8+ |
| Computer Vision | OpenCV (cv2) | 4.x |
| ML Models | scikit-learn | 1.x |
| Serial Communication | pyserial | 3.x |
| Dobot Control | pydobot | latest |
| Queue | collections.deque | stdlib |
| Threading | threading | stdlib |
| Model Persistence | joblib | stdlib |
| Numerical | numpy | 1.x |

---

## Module Structure

```
main.py                 → entry point, initializes all modules, starts main loop
camera.py               → webcam init, frame capture, ROI extraction
classifier.py           → feature extraction, KNN+SVM inference pipeline
esp32_controller.py     → serial read/write, IR event parsing, servo commands
dobot_controller.py     → belt start/stop, arm pickup/drop sequence
queue_manager.py        → color queue, enqueue/dequeue logic
dashboard.py            → optional live OpenCV display window
config.py               → all constants, pin names, distances, thresholds
```

---

## config.py — All Constants

```python
# Serial
ESP32_PORT = 'COM3'          # Windows: COMx, Linux/Mac: /dev/ttyUSBx
ESP32_BAUD = 115200

# Dobot
DOBOT_PORT = 'COM4'

# Camera
CAMERA_INDEX = 0
CAPTURE_DELAY = 0.15         # seconds after IR1 before capture (centering delay)

# ML
DETECTION_MIN_AREA = 5000     # minimum contour area in pixels to count as cube
DETECTION_PADDING = 15        # padding in pixels around bounding box crop
KNN_RATIO_THRESHOLD = 0.7     # distance ratio threshold (Lowe's ratio test)
SVM_PROBA_THRESHOLD = 0.6     # fallback probability threshold
CLASSES = ['green', 'blue', 'yellow', 'red']  # physical sorting target classes

# Servo timing
SERVO_PUSH_HOLD_MS = 400     # milliseconds servo stays extended

# Dobot arm positions (fill after physical calibration)
ARM_HOME       = (x, y, z, r)
ARM_PICKUP     = (x, y, z, r)
ARM_REJECT_BOX = (x, y, z, r)
ARM_LIFT_Z     = z + 40      # lift height before moving

# Belt
BELT_SPEED = 0.5             # 0.0-1.0, set once and fixed
BELT_DIRECTION = 1           # 1 = forward
```

---

## Software Pipeline — Step by Step

### Step 1 — Initialization
```
main.py starts
├── Load KNN model from models/knn_model.pkl
├── Load SVM model from models/svm_model.pkl
├── Open serial connection to ESP32
├── Open Dobot connection
├── Open webcam (VideoCapture)
├── Initialize empty color_queue (deque)
├── Start serial listener thread
└── Start Dobot belt
```

### Step 2 — Serial Listener Thread (runs continuously)
```
Thread loops forever reading serial port
├── Receives "IR1\n" → calls on_ir1_triggered()
├── Receives "IR2\n" → calls on_ir2_triggered()
└── Receives "IR3\n" → calls on_ir3_triggered()
```

### Step 3 — IR1 Handler (camera zone)
```
on_ir1_triggered():
├── Spawns threading.Timer(CAPTURE_DELAY, worker_thread) to avoid blocking serial read:
│   ├── Capture one frame from webcam
│   ├── Detect cube dynamically using HSV mask (S > 80, V > 60)
│   ├── Find largest contour (> 5000 px²) and get padded bounding box
│   ├── Crop cube image and extract normalized HSV histograms (3 channels × 32 bins = 96-dim vector)
│   ├── Run KNN (k=3) -> compute distance ratio (nearest / 2nd-nearest)
│   ├── If ratio < 0.7: Return KNN classification result
│   └── Else (ratio >= 0.7): Escalate to SVM fallback (RBF kernel)
│       ├── If max probability >= 0.6: Return SVM classification result
│       └── Else: Return "unknown"
└── Append returned color string to color_queue
```

### Step 4 — IR2 Handler (Green/Blue zone)
```
on_ir2_triggered():
├── If queue empty → return (no cube classified yet — edge case)
├── Peek front of queue (do not dequeue yet)
├── If color == 'green'
│   ├── Dequeue
│   └── Send "SG\n" to ESP32 → Green servo fires
├── If color == 'blue'
│   ├── Dequeue
│   └── Send "SB\n" to ESP32 → Blue servo fires
└── Else (Y, R, unknown) → do nothing, let cube pass through
```

### Step 5 — IR3 Handler (Yellow/Red zone)
```
on_ir3_triggered():
├── If queue empty → return
├── Peek front of queue
├── If color == 'yellow'
│   ├── Dequeue
│   └── Send "SY\n" to ESP32 → Yellow servo fires
├── If color == 'red'
│   ├── Dequeue
│   └── Send "SR\n" to ESP32 → Red servo fires
└── If color == 'unknown'
    ├── Dequeue
    ├── Stop belt (Dobot SDK)
    ├── Run arm_remove_sequence()
    └── Start belt (Dobot SDK)
```

### Step 6 — Arm Remove Sequence
```
arm_remove_sequence():
├── Move arm to ARM_PICKUP (x,y,z)
├── Wait until arm arrives
├── Vacuum ON
├── Sleep 0.8s (suction grip time)
├── Move arm to (ARM_PICKUP_X, ARM_PICKUP_Y, ARM_LIFT_Z) — lift
├── Wait
├── Move arm to ARM_REJECT_BOX
├── Wait
├── Vacuum OFF
├── Sleep 0.5s
├── Move arm to ARM_HOME
└── Wait
```

---

## Queue System — Handling Multiple Simultaneous Cubes

The queue is the core of continuous operation.

```
color_queue = deque()

Timeline example:
t=0s  Cube1 breaks IR1 → classify → queue: [RED]
t=1s  Cube2 breaks IR1 → classify → queue: [RED, GREEN]
t=2s  Cube1 breaks IR2 → peek=RED → not G/B → pass
t=3s  Cube2 breaks IR2 → peek=RED → not G/B → pass
t=4s  Cube1 breaks IR3 → peek=RED → dequeue → fire RED servo → queue: [GREEN]
t=5s  Cube2 breaks IR2 → peek=GREEN → dequeue → fire GREEN servo → queue: []
```

Queue guarantees FIFO order. First cube classified = first cube sorted. No mix-ups even with multiple cubes on belt.

---

## Threading Model

```
Main Thread
└── Initialization → starts belt → waits

Serial Listener Thread (daemon)
└── Reads ESP32 serial continuously
    └── Fires IR handlers on events

IR Handlers
└── Run in serial listener thread context
    ├── on_ir1 → spawns brief capture/classify work
    ├── on_ir2 → queue peek + optional serial write
    └── on_ir3 → queue peek + optional serial write or arm sequence

Dobot arm sequence
└── Blocking calls — belt is stopped during arm operation
    so no new cubes arrive while arm is moving
```

Note: queue operations (deque) in Python are thread-safe for single append/popleft operations. No explicit lock needed.

---

## Classification Pipeline Detail

```
Input: raw BGR frame from webcam

Step 1 — Normalize Input Size
Resize frame to 640×480 (standardize frame size across cameras)

Step 2 — Convert to HSV
cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

Step 3 — HSV Saturation/Value Masking
lower_bound = np.array([0, 80, 60])
upper_bound = np.array([180, 255, 255])
mask = cv2.inRange(hsv, lower_bound, upper_bound)

Step 4 — Morphological Opening
kernel = np.ones((5,5), np.uint8)
cleaned_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

Step 5 — Contour Detection & Filtering
contours, _ = cv2.findContours(cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
Filter: retain contours with cv2.contourArea(c) > 5000.
Select: largest contour from the filtered list (representing the cube).

Step 6 — Crop Bounding Box with Padding
x, y, w, h = cv2.boundingRect(largest_contour)
x1 = max(0, x - 15), y1 = max(0, y - 15)
x2 = min(640, x + w + 15), y2 = min(480, y + h + 15)
cropped_cube = frame[y1:y2, x1:x2]

Step 7 — Extract Center 50% Patch
hc, wc = cropped_cube.shape[:2]
center_patch = cropped_cube[int(hc*0.25):int(hc*0.75), int(wc*0.25):int(wc*0.75)]

Step 8 — Extract Normalised HSV Histograms
patch_hsv = cv2.cvtColor(center_patch, cv2.COLOR_BGR2HSV)
hist_h = cv2.calcHist([patch_hsv], [0], None, [32], [0, 180])
hist_s = cv2.calcHist([patch_hsv], [1], None, [32], [0, 256])
hist_v = cv2.calcHist([patch_hsv], [2], None, [32], [0, 256])
Normalize each histogram to sum to 1.
Concatenate into a 96-dimensional feature vector.

Step 9 — Two-Stage Classification Cascade
1. KNN (k=3): Get 2 nearest neighbor distances: d1, d2.
   If d1 / (d2 + 1e-7) < 0.7: Return KNN class prediction.
2. SVM Fallback (RBF): Run svm.predict_proba().
   If max probability >= 0.6: Return SVM class prediction.
   Else: Return "unknown".

Step 10 — Return (color_label, confidence, model_used)
```

---

## ESP32 Firmware Logic

ESP32 runs MicroPython or Arduino C. Its only jobs:

```
1. Monitor IR pins for LOW signal
2. Send IR event string to laptop via serial
3. Receive servo command string from laptop
4. Fire correct servo PWM sequence
```

Servo fire sequence on ESP32:
```
Receive "SG\n"
→ GPIO25 PWM → 0° (push position)
→ delay 400ms
→ GPIO25 PWM → 90° (neutral)
→ ready for next command
```

ESP32 does NOT decide which servo to fire. Laptop decides. ESP32 just executes.

---

## Error Handling

| Scenario | Handling |
|---|---|
| IR1 triggers but classification fails | Log error, do not enqueue, belt continues |
| Queue empty at IR2/IR3 | Ignore trigger, log warning |
| ESP32 serial disconnect | Exception caught, log error, attempt reconnect |
| Dobot disconnect | Exception caught, emergency belt stop |
| Camera frame read failure | Retry 3 times, log error if all fail |
| Unknown color at IR3 | Belt stop → arm remove → belt resume |

---

## Dashboard (Optional — dashboard.py)

Live OpenCV window showing:
```
┌─────────────────────────────────────┐
│  LIVE FEED          [ROI box drawn] │
│                                     │
│  Last Detection: 🟢 GREEN           │
│  Model Used:     KNN                │
│  Confidence:     94.3%              │
│                                     │
│  Queue:  [RED, BLUE]                │
│                                     │
│  Sort Count:                        │
│  Green:   12  │  Blue:   8          │
│  Yellow:   6  │  Red:   15          │
│  Unknown:  2                        │
└─────────────────────────────────────┘
```

Runs in main thread using cv2.imshow(). Updated every frame. Press Q to quit.

---

## Startup Sequence

```
1. Connect Dobot USB
2. Connect ESP32 USB
3. Connect Webcam USB
4. Power on 6V battery (servo power)
5. Run: python main.py
6. System auto-detects COM ports
7. Belt starts automatically
8. Place cubes on belt
```

---

## Dependencies (requirements.txt)

```
opencv-python>=4.5.0
scikit-learn>=1.0.0
numpy>=1.21.0
pyserial>=3.5
pydobot>=1.3.0
joblib>=1.0.0
```
