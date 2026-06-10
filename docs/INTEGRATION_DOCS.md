# Integration Documentation
## Dobot Color Sorting System — How All Parts Connect

---

## System Components Map

```
┌─────────────────────────────────────────────────────────┐
│                        LAPTOP                           │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐   │
│  │ ML Model │  │  Queue   │  │   Dobot Controller │   │
│  │ KNN+SVM  │→ │ Manager  │→ │   Belt + Arm API   │   │
│  └──────────┘  └──────────┘  └────────────────────┘   │
│       ↑              ↑↓               ↑↓               │
│  ┌──────────┐  ┌──────────┐           │                │
│  │  Camera  │  │  ESP32   │           │                │
│  │ Capture  │  │Controller│           │                │
│  └──────────┘  └──────────┘           │                │
└───────┬──────────────┬────────────────┼────────────────┘
        │              │                │
      USB            USB             USB
        │              │                │
   ┌────┴────┐   ┌──────┴──────┐  ┌────┴──────┐
   │ Webcam  │   │    ESP32    │  │   Dobot   │
   │ C270    │   │  DevKit     │  │ Magician  │
   └─────────┘   └──────┬──────┘  └─────┬─────┘
                        │               │
              ┌─────────┴──────┐   ┌────┴──────┐
              │   Breadboard   │   │   Belt    │
              │  (GND + power) │   │   + Arm   │
              └────────────────┘   └───────────┘
                   │        │
           ┌───────┴─┐  ┌───┴──────┐
           │ 6V Batt │  │ IR + SG90│
           └─────────┘  └──────────┘
```

---

## Integration Points

### 1. Laptop ↔ ESP32
- **Physical:** USB micro cable
- **Protocol:** Serial UART at 115200 baud
- **Library:** pyserial
- **Direction:** Bidirectional
- **ESP32 → Laptop:** IR sensor events (`IR1\n`, `IR2\n`, `IR3\n`)
- **Laptop → ESP32:** Servo commands (`SG\n`, `SB\n`, `SY\n`, `SR\n`)
- **Port:** Auto-detected by scanning COM ports for ESP32/CP210x descriptor

### 2. Laptop ↔ Dobot
- **Physical:** Dobot USB cable (included with Dobot)
- **Protocol:** pydobot SDK over USB serial
- **Library:** pydobot
- **Direction:** Bidirectional (commands out, position feedback in)
- **Laptop → Dobot:** Belt speed/direction, arm move commands, vacuum on/off
- **Port:** Auto-detected by scanning for CP210 or Dobot descriptor

### 3. Laptop ↔ Webcam
- **Physical:** USB cable
- **Protocol:** UVC (USB Video Class) — standard webcam protocol
- **Library:** OpenCV cv2.VideoCapture(0)
- **Direction:** Laptop reads frames from webcam
- **Trigger:** Software-triggered capture (not continuous streaming to ML)

### 4. ESP32 ↔ IR Sensors
- **Physical:** Jumper wires (Male to Female)
- **Protocol:** Digital GPIO (HIGH/LOW)
- **Direction:** IR sensor → ESP32 (input only)
- **Behavior:** FC-51 OUT pin goes LOW when object detected

### 5. ESP32 ↔ Servo Motors
- **Physical:** Jumper wires (Male to Male) or servo extension cables
- **Protocol:** PWM signal
- **Direction:** ESP32 → Servo (output only)
- **Signal:** 50Hz PWM, pulse width 500-2500μs (maps to 0°-180°)

### 6. ESP32 ↔ Breadboard
- **Physical:** Jumper wire from ESP32 GND pin to breadboard - rail
- **Purpose:** Common ground between ESP32 logic and servo power

### 7. Battery ↔ Breadboard ↔ Servos
- **Physical:** Battery wires twisted into breadboard rails
- **Purpose:** 6V power distribution to all 4 servo RED wires

---

## Data Flow — Complete End to End

```
CUBE PLACED ON BELT
        ↓
Belt moves cube forward (Dobot belt running at fixed speed)
        ↓
Cube passes FC-51 IR Sensor 1
FC-51 OUT → LOW signal
        ↓
ESP32 GPIO34 reads LOW
ESP32 sends "IR1\n" via USB Serial
        ↓
Python (esp32_controller.py) reads "IR1\n"
Calls on_ir1_triggered()
        ↓
Spawns threading.Timer(0.15s) to run in worker thread
camera.py captures one frame
classifier.py detects cube dynamically (HSV mask + contour) and extracts center 50% patch HSV histogram (96 features)
KNN predicts → confidence check (distance ratio test) → SVM if ratio >= 0.7
Color result: e.g. "green"
        ↓
queue_manager.py appends "green" to deque
        ↓
[cube travels ~20cm to IR2 zone]
        ↓
Cube passes FC-51 IR Sensor 2
ESP32 sends "IR2\n"
        ↓
on_ir2_triggered()
queue_manager peeks front → "green"
"green" is in [G, B] → dequeue
esp32_controller sends "SG\n"
        ↓
ESP32 GPIO25 → PWM 0° (push)
→ delay 400ms
→ PWM 90° (neutral)
        ↓
CUBE IN GREEN BIN ✅
```

---

## Unknown Cube Data Flow

```
Color classified as "unknown"
Appended to queue
        ↓
Cube passes IR2 → peeked → not G/B → ignored → cube passes
        ↓
Cube passes IR3
on_ir3_triggered()
queue_manager peeks → "unknown"
        ↓
dobot_controller.stop_belt()
arm_remove_sequence() runs
        ↓
dobot_controller.start_belt()
UNKNOWN CUBE IN REJECT BOX ✅
```

---

## Port Auto-Detection Logic

```python
import serial.tools.list_ports

def find_port(keywords):
    ports = serial.tools.list_ports.comports()
    for port in ports:
        for keyword in keywords:
            if keyword.lower() in port.description.lower():
                return port.device
    return None

esp32_port  = find_port(['CP2102', 'CP210', 'ESP32', 'USB Serial'])
dobot_port  = find_port(['CP210', 'Dobot', 'Silicon Labs'])
```

If both devices use the same CP210x chip (common), manually assign ports:
```python
# Check Device Manager / dmesg and hardcode if needed
ESP32_PORT = 'COM3'
DOBOT_PORT = 'COM4'
```

---

## Timing Integration

All timing derived from fixed belt speed (no dynamic measurement needed):

```
Belt speed: 0.5 (Dobot units) = approx X cm/s (calibrate physically)

IR1 → IR2 distance: 20cm
Travel time IR1→IR2: 20cm / X cm/s = T1 seconds

IR1 → IR3 distance: 40cm
Travel time IR1→IR3: T2 seconds

Classification latency: ~100-200ms (camera + KNN/SVM)
Capture delay: 150ms (centering)
Total IR1 to color queued: ~350ms

Since T1 is typically 1-3 seconds at any reasonable belt speed,
classification always completes before cube reaches IR2.
No race conditions.
```

---

## Initialization Order (Critical)

Must initialize in this exact order to avoid port conflicts:

```python
# 1. Load ML models (no hardware dependency)
knn = joblib.load('models/knn_model.pkl')
svm = joblib.load('models/svm_model.pkl')

# 2. Open webcam
cap = cv2.VideoCapture(CAMERA_INDEX)

# 3. Connect ESP32
esp32 = serial.Serial(ESP32_PORT, ESP32_BAUD, timeout=1)
time.sleep(2)  # ESP32 resets on serial connect — wait for boot

# 4. Connect Dobot
device = Dobot(port=DOBOT_PORT, verbose=False)

# 5. Initialize queue
color_queue = deque()

# 6. Start serial listener thread
listener = threading.Thread(target=serial_listener, daemon=True)
listener.start()

# 7. Start belt
device.conveyor_belt(BELT_SPEED, BELT_DIRECTION)

# System is now live
```

**Why ESP32 needs 2 second delay:** ESP32 resets (reboots) when a serial connection is opened. If you send commands immediately, ESP32 misses them. Always wait 2 seconds after opening serial port.

---

## Shutdown Sequence

```python
def shutdown():
    device.conveyor_belt(0, 1)      # stop belt
    device.suck(False)              # ensure vacuum off
    device.move_to(*ARM_HOME, wait=True)  # arm to safe position
    esp32.close()                   # close serial
    cap.release()                   # release camera
    cv2.destroyAllWindows()         # close display
    device.close()                  # close Dobot
```

Call on KeyboardInterrupt (Ctrl+C) or Q key press.

---

## Known Integration Gotchas

| Issue | Cause | Fix |
|---|---|---|
| ESP32 not detected | Wrong COM port | Check Device Manager, update config |
| ESP32 misses first commands | ESP32 boot delay | Add time.sleep(2) after serial open |
| Servos twitch randomly | Missing common ground | Connect ESP32 GND to breadboard - rail |
| Dobot port same as ESP32 | Both use CP210x | Unplug one, check port, replug, assign manually |
| IR sensor always LOW | Sensitivity too high | Adjust FC-51 potentiometer |
| IR sensor never LOW | Sensitivity too low | Adjust FC-51 potentiometer |
| Queue out of order | Race condition on IR3 | Ensure serial listener is single thread |
| Camera captures wrong moment | CAPTURE_DELAY wrong | Increase delay if cube not centered in camera view when frame is captured |
