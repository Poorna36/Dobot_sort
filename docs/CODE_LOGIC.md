# Code Logic & Software Architecture Specification
## Dobot Color Sorter — Complete Program Listings & Reference Skeletal Code

This document defines the software architecture, the multi-threaded execution model, and provides full reference listings for both the Python scripts on the laptop and the C++ firmware on the ESP32.

---

## 1. Threading & Queue Architecture

The laptop software runs as a single process with two active threads to prevent hardware-blocking lag:

1. **Main Orchestration Thread:**
   - Performs system initialization, setups the camera, serial, and Dobot connections.
   - Starts the conveyor belt.
   - Enters a blocking loop for user input (e.g. listens for 'q' to shut down gracefully).
2. **Serial Listener Thread:**
   - Runs as a background daemon loop reading lines from the ESP32 serial port.
   - Parses the messages (`IR1`, `IR2`, `IR3`).
   - Dispatches handlers asynchronously.
   - For camera capture (IR1), it spawns a non-blocking `threading.Timer` thread to sleep for `CAPTURE_DELAY` (150ms) and perform classification, which prevents blocking serial read cycles.

### 1.1 FIFO Queue System
- Implemented using a thread-safe `collections.deque` object.
- Elements added: Strings (`'green'`, `'blue'`, `'yellow'`, `'red'`, or `'unknown'`).
- Enqueued when classification completes after an `IR1` event.
- Peeked/Dequeued when `IR2` or `IR3` sensors detect a cube.

```
       CUBE ON BELT
            │
            ▼
         [ IR1 ] ──(Serial)──► [ Serial Listener Thread ]
                                         │
                                   (Timer 150ms)
                                         │
                                         ▼
                               [ Capture & Classify ]
                                         │
                                   (color_label)
                                         │
                                         ▼
                               ┌──────────────────┐
                               │ FIFO Color Queue │
                               │  [G, B, Y, R]    │
                               └────────┬─────────┘
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
          [ IR2 ] ──(Serial)──► [ Peek / Dequeue ]              [ IR3 ] ──(Serial)──► [ Peek / Dequeue ]
                                        │                                                     │
                                 Is Green/Blue?                                        Is Yellow/Red?
                                        │                                                     │
                        YES ──► Stop Belt (1.5s)                          YES ──► Stop Belt (1.5s)
                              └─► Send "1L" or "1R"                                └─► Send "2L" or "2R"
                              └─► Wait for servo (4.5s)                             └─► Wait for servo (4.5s)
                              └─► Start Belt                                         └─► Start Belt
                                                                                              │
                                                                                      Is Unknown?
                                                                                              │
                                                                                   YES ──► Stop Belt
                                                                                     ──► Run Arm sequence
                                                                                     ──► Start Belt
```

---

## 2. Serial Communication Protocol

- **Baud Rate:** `115200`
- **Port Settings:** 8 Data bits, 1 Stop bit, No parity.
- **Delimiter:** Newline character `\n` (CRLF stripped automatically).

### 2.1 Message Packets

| Message Type | Direction | String | Description |
|---|---|---|---|
| **IR1 Sensor Event** | ESP32 $\rightarrow$ Laptop | `IR1\n` | Cube detected at camera zone |
| **IR2 Sensor Event** | ESP32 $\rightarrow$ Laptop | `IR2\n` | Cube detected at Servo 1 zone |
| **IR3 Sensor Event** | ESP32 $\rightarrow$ Laptop | `IR3\n` | Cube detected at Servo 2 zone |
| **Servo 1 Left Cmd** | Laptop $\rightarrow$ ESP32 | `1L\n` | Servo 1 at IR2 pushes left (Green) |
| **Servo 1 Right Cmd** | Laptop $\rightarrow$ ESP32 | `1R\n` | Servo 1 at IR2 pushes right (Blue) |
| **Servo 2 Left Cmd** | Laptop $\rightarrow$ ESP32 | `2L\n` | Servo 2 at IR3 pushes left (Yellow) |
| **Servo 2 Right Cmd** | Laptop $\rightarrow$ ESP32 | `2R\n` | Servo 2 at IR3 pushes right (Red) |

---

## 3. Reference Program Listings (Python Code Skeletal System)

### 3.1 `config.py`
Contains all static parameters, coordinates, and thresholds.
```python
# config.py
import os

# Hardware Communication Ports
ESP32_PORT = 'COM3'
ESP32_BAUD = 115200
DOBOT_PORT = 'COM4'

# Camera Settings
CAMERA_INDEX = 0
CAPTURE_DELAY = 0.15  # Delay (s) for cube centering

# ML Detection and Thresholds
DETECTION_MIN_AREA = 5000     # px^2
DETECTION_PADDING = 15        # px
KNN_RATIO_THRESHOLD = 0.7     # Lowe's distance ratio
SVM_PROBA_THRESHOLD = 0.6     # SVM classification cutoff
CLASSES = ['green', 'blue', 'yellow', 'red']

# Servo System Configuration (2-Servo Design)
CONVEYOR_STOP_DURATION = 1.5  # seconds - belt stop when IR2/IR3 triggers
SERVO_ALIGN_DURATION = 4.5     # seconds - servo push cycle time
SERVO_NEUTRAL_ANGLE = 90      # degrees - placeholder, calibrate after hardware setup
SERVO_PUSH_LEFT_ANGLE = 0     # degrees - placeholder, calibrate after hardware setup
SERVO_PUSH_RIGHT_ANGLE = 180  # degrees - placeholder, calibrate after hardware setup

# Dobot Conveyor Belt Configurations
BELT_SPEED = 0.5    # Speed ratio for Dobot conveyor (0.0 to 1.0)
BELT_DIRECTION = 1  # 1 = Forward, -1 = Reverse

# Dobot Cartesian Coordinates: (X, Y, Z, R)
# Note: Physical values must be updated after teacher mode calibration
ARM_HOME = (200.0, 0.0, 50.0, 0.0)
ARM_PICKUP = (230.0, -120.0, -45.0, 0.0)
ARM_PICKUP_Z_DOWN = -45.0
ARM_PICKUP_Z_UP = -5.0
ARM_REJECT_BOX = (150.0, 200.0, 20.0, 0.0)
```

### 3.2 `classifier.py`
Handles off-line training, image preprocessing, and two-stage classification inference.
```python
# classifier.py
import cv2
import numpy as np
import joblib
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
import config

def detect_cube(frame):
    """
    Locates the cube dynamically using HSV masking and contour filtering.
    Returns: cropped_cube BGR image, and bounding box coordinates (x1, y1, x2, y2).
             If no cube is found, returns (None, None).
    """
    # Resize to normalize area calculations
    resized = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    
    # Saturation/Value threshold mask
    lower_bound = np.array([0, 80, 60], dtype=np.uint8)
    upper_bound = np.array([180, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_bound, upper_bound)
    
    # Morphological Opening (Erosion then Dilation)
    kernel = np.ones((5, 5), dtype=np.uint8)
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    # Contour Finding
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [c for c in contours if cv2.contourArea(c) > config.DETECTION_MIN_AREA]
    
    if not valid_contours:
        return None, None
        
    largest_contour = max(valid_contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest_contour)
    
    # Apply padding and boundary clamps
    x1 = max(0, x - config.DETECTION_PADDING)
    y1 = max(0, y - config.DETECTION_PADDING)
    x2 = min(640, x + w + config.DETECTION_PADDING)
    y2 = min(480, y + h + config.DETECTION_PADDING)
    
    cropped_cube = resized[y1:y2, x1:x2]
    return cropped_cube, (x1, y1, x2, y2)

def extract_features(cropped_cube):
    """
    Extracts the normalized HSV histogram (96-dim) from the center 50% patch.
    """
    hc, wc = cropped_cube.shape[:2]
    ys, ye = int(hc * 0.25), int(hc * 0.75)
    xs, xe = int(wc * 0.25), int(wc * 0.75)
    center_patch = cropped_cube[ys:ye, xs:xe]
    
    patch_hsv = cv2.cvtColor(center_patch, cv2.COLOR_BGR2HSV)
    
    hist_h = cv2.calcHist([patch_hsv], [0], None, [32], [0, 180])
    hist_s = cv2.calcHist([patch_hsv], [1], None, [32], [0, 256])
    hist_v = cv2.calcHist([patch_hsv], [2], None, [32], [0, 256])
    
    # Normalize
    hist_h /= (np.sum(hist_h) + 1e-7)
    hist_s /= (np.sum(hist_s) + 1e-7)
    hist_v /= (np.sum(hist_v) + 1e-7)
    
    # Concatenate to 96 dimensions
    feature_vector = np.concatenate([hist_h.flatten(), hist_s.flatten(), hist_v.flatten()])
    return feature_vector

class TwoStageClassifier:
    def __init__(self, knn_path, svm_path):
        self.knn = joblib.load(knn_path)
        self.svm = joblib.load(svm_path)
        
    def classify(self, feature_vector):
        """
        Runs the KNN -> SVM cascade.
        Returns: color string (label), confidence score (float), and model name (string)
        """
        features = feature_vector.reshape(1, -1)
        
        # Stage 1: KNN (k=3) Neighbors Check
        distances, indices = self.knn.kneighbors(features)
        d1 = distances[0][0]
        d2 = distances[0][1]
        ratio = d1 / (d2 + 1e-7)
        
        if ratio < config.KNN_RATIO_THRESHOLD:
            prediction = self.knn.predict(features)[0]
            # Convert ratio to pseudo-confidence (smaller ratio = higher confidence)
            confidence = max(0.0, min(1.0, 1.0 - ratio))
            return prediction, confidence, "KNN"
            
        # Stage 2: SVM Fallback (RBF)
        svm_proba = self.svm.predict_proba(features)[0]
        max_idx = np.argmax(svm_proba)
        max_prob = svm_proba[max_idx]
        
        if max_prob >= config.SVM_PROBA_THRESHOLD:
            prediction = self.svm.classes_[max_idx]
            return prediction, max_prob, "SVM"
        else:
            return "unknown", max_prob, "SVM_REJECT"

def train_models(dataset_path, output_knn_path, output_svm_path):
    """
    Offline training utility. Reads augmented dataset, compiles vectors, and saves .pkl files.
    """
    X = []
    y = []
    
    for label in config.CLASSES:
        label_dir = os.path.join(dataset_path, 'augmented', label)
        if not os.path.exists(label_dir):
            continue
        for file in os.listdir(label_dir):
            if file.endswith(('.jpg', '.png', '.jpeg')):
                img_path = os.path.join(label_dir, file)
                img = cv2.imread(img_path)
                cropped, _ = detect_cube(img)
                if cropped is not None:
                    feats = extract_features(cropped)
                    X.append(feats)
                    y.append(label)
                    
    X = np.array(X)
    y = np.array(y)
    
    # Train KNN (k=3)
    knn = KNeighborsClassifier(n_neighbors=3, metric='euclidean')
    knn.fit(X, y)
    joblib.dump(knn, output_knn_path)
    
    # Train SVM (RBF)
    svm = SVC(kernel='rbf', C=10.0, probability=True)
    svm.fit(X, y)
    joblib.dump(svm, output_svm_path)
    print("Models trained and persisted successfully.")
```

### 3.3 `camera.py`
Interfaces with OpenCV to grab frames from the webcam.
```python
# camera.py
import cv2
import config

class CameraWrapper:
    def __init__(self):
        self.cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if not self.cap.isOpened():
            raise IOError("Webcam cannot be opened. Check index.")
            
    def get_frame(self):
        """
        Grabs a single BGR frame.
        """
        ret, frame = self.cap.read()
        if not ret:
            return None
        return frame
        
    def release(self):
        self.cap.release()
```

### 3.4 `esp32_controller.py`
Handles serial data IO and command translation.
```python
# esp32_controller.py
import serial
import time
import logging

class ESP32Controller:
    def __init__(self, port, baudrate):
        self.serial = serial.Serial(port, baudrate, timeout=1.0)
        # ESP32 auto-resets on connection. Boot takes ~2 seconds.
        time.sleep(2.0)
        self.serial.reset_input_buffer()
        logging.info("ESP32 Communication initialized.")
        
    def read_line(self):
        """
        Reads newline-terminated strings from serial buffer.
        """
        if self.serial.in_waiting > 0:
            try:
                line = self.serial.readline().decode('utf-8').strip()
                return line
            except Exception as e:
                logging.error(f"Serial read error: {e}")
        return None
        
    def send_servo_command(self, color):
        """
        Translates a color label into the corresponding ESP32 servo command.
        2-servo design: Servo 1 at IR2 (green=left, blue=right), Servo 2 at IR3 (yellow=left, red=right).
        """
        commands = {
            'green': '1L\n',  # Servo 1 push left
            'blue': '1R\n',   # Servo 1 push right
            'yellow': '2L\n', # Servo 2 push left
            'red': '2R\n'     # Servo 2 push right
        }
        cmd = commands.get(color.lower())
        if cmd:
            self.serial.write(cmd.encode('utf-8'))
            self.serial.flush()
            logging.info(f"Transmitted command: {cmd.strip()} for color {color}")
            
    def close(self):
        self.serial.close()
```

### 3.5 `dobot_controller.py`
Interfaces with the `pydobot` SDK to run the conveyor belt and control vacuum pickup.
```python
# dobot_controller.py
import time
import logging
from pydobot import Dobot
import config

class DobotController:
    def __init__(self, port):
        self.device = Dobot(port=port, verbose=False)
        logging.info("Dobot Magician connected.")
        
    def start_belt(self):
        # Starts conveyor belt forward
        self.device.conveyor_belt(config.BELT_SPEED, config.BELT_DIRECTION)
        
    def stop_belt(self):
        # Stops conveyor belt
        self.device.conveyor_belt(0.0, config.BELT_DIRECTION)
        
    def run_arm_reject_sequence(self):
        """
        Executes the non-colliding pickup and deposit movements for unknown cubes.
        """
        try:
            # 1. Stop belt
            self.stop_belt()
            time.sleep(0.5) # Allow belt oscillation to settle
            
            # 2. Hover above pickup point
            self.device.move_to(
                config.ARM_PICKUP[0], 
                config.ARM_PICKUP[1], 
                config.ARM_PICKUP_Z_UP, 
                config.ARM_PICKUP[3], 
                wait=True
            )
            
            # 3. Descend to touch cube surface
            self.device.move_to(
                config.ARM_PICKUP[0], 
                config.ARM_PICKUP[1], 
                config.ARM_PICKUP_Z_DOWN, 
                config.ARM_PICKUP[3], 
                wait=True
            )
            
            # 4. Turn vacuum ON
            self.device.suck(True)
            time.sleep(0.8) # Grip seal latency
            
            # 5. Lift cube vertically
            self.device.move_to(
                config.ARM_PICKUP[0], 
                config.ARM_PICKUP[1], 
                config.ARM_PICKUP_Z_UP, 
                config.ARM_PICKUP[3], 
                wait=True
            )
            
            # 6. Move to reject box coordinates
            self.device.move_to(
                config.ARM_REJECT_BOX[0], 
                config.ARM_REJECT_BOX[1], 
                config.ARM_REJECT_BOX[2], 
                config.ARM_REJECT_BOX[3], 
                wait=True
            )
            
            # 7. Release vacuum
            self.device.suck(False)
            time.sleep(0.5) # Grip release delay
            
            # 8. Return home safely
            self.device.move_to(
                config.ARM_HOME[0], 
                config.ARM_HOME[1], 
                config.ARM_HOME[2], 
                config.ARM_HOME[3], 
                wait=True
            )
            
            # 9. Restart belt
            self.start_belt()
        except Exception as e:
            logging.error(f"Dobot Arm control failure: {e}")
            
    def shutdown(self):
        self.stop_belt()
        self.device.suck(False)
        self.device.move_to(*config.ARM_HOME, wait=True)
        self.device.close()
```

### 3.6 `main.py`
Binds all components together, implements asynchronous camera timer triggers, parses serial, and handles the FIFO queue.
```python
# main.py
import threading
import time
import logging
from collections import deque
import config
from classifier import detect_cube, extract_features, TwoStageClassifier
from camera import CameraWrapper
from esp32_controller import ESP32Controller
from dobot_controller import DobotController

# Setup logging formats
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class SystemOrchestrator:
    def __init__(self):
        self.color_queue = deque()
        self.running = False
        
        # Load classification models
        self.model = TwoStageClassifier('models/knn_model.pkl', 'models/svm_model.pkl')
        
        # Connect hardware components
        self.camera = CameraWrapper()
        self.esp32 = ESP32Controller(config.ESP32_PORT, config.ESP32_BAUD)
        self.dobot = DobotController(config.DOBOT_PORT)
        
    def start(self):
        self.running = True
        
        # Start serial listener daemon thread
        self.serial_thread = threading.Thread(target=self.serial_loop, daemon=True)
        self.serial_thread.start()
        
        # Start conveyor belt movement
        self.dobot.start_belt()
        logging.info("Color Sorting System is fully active.")
        
    def capture_and_classify_worker(self):
        """
        Deferred execution thread worker. Captured, cropped, extracts features, 
        and runs cascade classification. Appends result to queue.
        """
        logging.info("Executing timed image capture...")
        frame = self.camera.get_frame()
        if frame is None:
            logging.error("Failed to read frame from webcam.")
            return
            
        cropped, bbox = detect_cube(frame)
        if cropped is None:
            logging.warning("IR1 triggered, but no cube could be located via HSV mask.")
            # Enqueue a fallback "unknown" to maintain alignment
            self.color_queue.append("unknown")
            return
            
        feats = extract_features(cropped)
        color, confidence, model_used = self.model.classify(feats)
        logging.info(f"Classification result: {color.upper()} ({confidence*100:.1f}%) via {model_used}")
        
        self.color_queue.append(color)
        
    def handle_ir1(self):
        """
        Fires on camera zone detection. Spawns a timer thread to allow the 
        conveyor to center the cube under the webcam.
        """
        logging.info(f"IR1 Triggered. Scheduling capture in {config.CAPTURE_DELAY}s.")
        threading.Timer(config.CAPTURE_DELAY, self.capture_and_classify_worker).start()
        
    def handle_ir2(self):
        """
        Fires on Servo 1 zone (near IR2). Stops conveyor, allows servo alignment,
        then pushes cube left (green) or right (blue).
        """
        logging.info("IR2 Triggered.")
        if not self.color_queue:
            logging.warning("IR2 event received, but color queue is empty. Cube out of alignment.")
            return
            
        next_color = self.color_queue[0] # Peek front
        if next_color in ['green', 'blue']:
            # Stop conveyor for servo alignment
            self.dobot.stop_belt()
            time.sleep(config.CONVEYOR_STOP_DURATION)
            
            # Send servo command
            self.color_queue.popleft() # Dequeue
            self.esp32.send_servo_command(next_color)
            
            # Wait for servo to complete push cycle
            time.sleep(config.SERVO_ALIGN_DURATION)
            
            # Restart conveyor
            self.dobot.start_belt()
        else:
            logging.info(f"Cube is {next_color.upper()}. Passing through IR2 zone.")
            
    def handle_ir3(self):
        """
        Fires on Servo 2 zone (near IR3). Stops conveyor, allows servo alignment,
        then pushes cube left (yellow) or right (red). Unknown cubes trigger arm.
        """
        logging.info("IR3 Triggered.")
        if not self.color_queue:
            logging.warning("IR3 event received, but color queue is empty.")
            return
            
        next_color = self.color_queue[0] # Peek front
        if next_color in ['yellow', 'red']:
            # Stop conveyor for servo alignment
            self.dobot.stop_belt()
            time.sleep(config.CONVEYOR_STOP_DURATION)
            
            # Send servo command
            self.color_queue.popleft() # Dequeue
            self.esp32.send_servo_command(next_color)
            
            # Wait for servo to complete push cycle
            time.sleep(config.SERVO_ALIGN_DURATION)
            
            # Restart conveyor
            self.dobot.start_belt()
        elif next_color == 'unknown':
            self.color_queue.popleft() # Dequeue
            logging.critical("UNKNOWN object detected at sorting limit. Initializing arm pickup.")
            self.dobot.run_arm_reject_sequence()
        else:
            logging.warning(f"Cube is {next_color.upper()}. Reached end of belt without being sorted!")
            # Dequeue to clear pipeline blockages
            self.color_queue.popleft()
            
    def serial_loop(self):
        """
        Continuous serial reading loop. Parses lines to trigger handlers.
        """
        while self.running:
            line = self.esp32.read_line()
            if line:
                if line == "IR1":
                    self.handle_ir1()
                elif line == "IR2":
                    self.handle_ir2()
                elif line == "IR3":
                    self.handle_ir3()
            time.sleep(0.01) # Yield CPU
            
    def stop(self):
        self.running = False
        self.dobot.shutdown()
        self.camera.release()
        self.esp32.close()
        logging.info("System shut down cleanly.")

if __name__ == '__main__':
    orchestrator = SystemOrchestrator()
    orchestrator.start()
    
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt captured. Initializing shutdown sequence.")
        orchestrator.stop()
```

---

## 4. ESP32 Arduino C++ Firmware

The firmware below must be compiled and uploaded to the ESP32 DevKit using the Arduino IDE. It uses the `ESP32Servo` library to resolve internal PWM timer conflicts.

```cpp
#include <ESP32Servo.h>

// Sensor digital input pins (FC-51 active low)
#define IR1_PIN 34   // Camera zone (IR1)
#define IR2_PIN 35   // Servo 1 zone (IR2)
#define IR3_PIN 32   // Servo 2 zone (IR3)

// SG90 Servo PWM signal output pins (2-servo design)
#define SERVO_1_PIN 25  // Servo 1 at IR2
#define SERVO_2_PIN 26  // Servo 2 at IR3

// Default neutral angle on startup (paddle parallel to belt)
#define DEFAULT_NEUTRAL 90

// Software Debounce duration in milliseconds
#define DEBOUNCE_MS  300

// Declared Servo instances
Servo servo1;
Servo servo2;

// Timing registers for debouncing
unsigned long lastIR1 = 0;
unsigned long lastIR2 = 0;
unsigned long lastIR3 = 0;

void setup() {
  Serial.begin(115200);

  // Configure sensors as simple inputs
  pinMode(IR1_PIN, INPUT);
  pinMode(IR2_PIN, INPUT);
  pinMode(IR3_PIN, INPUT);

  // Attach servo signals to PWM pins
  servo1.attach(SERVO_1_PIN);
  servo2.attach(SERVO_2_PIN);

  // Set all servo arms to default neutral position
  servo1.write(DEFAULT_NEUTRAL);
  servo2.write(DEFAULT_NEUTRAL);

  delay(500);
  Serial.println("ESP32 READY");
}

void loop() {
  unsigned long now = millis();

  // Evaluate Sensor 1 (Camera Zone)
  if (digitalRead(IR1_PIN) == LOW) {
    if (now - lastIR1 > DEBOUNCE_MS) {
      lastIR1 = now;
      Serial.println("IR1");
    }
  }

  // Evaluate Sensor 2 (Green/Blue Zone)
  if (digitalRead(IR2_PIN) == LOW) {
    if (now - lastIR2 > DEBOUNCE_MS) {
      lastIR2 = now;
      Serial.println("IR2");
    }
  }

  // Evaluate Sensor 3 (Yellow/Red Zone)
  if (digitalRead(IR3_PIN) == LOW) {
    if (now - lastIR3 > DEBOUNCE_MS) {
      lastIR3 = now;
      Serial.println("IR3");
    }
  }

  // Read incoming serial commands from laptop
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim(); // Strip carriage returns on Windows

    // Dynamic Protocol Format: "S<servo_number>:<angle>"
    // e.g. "S1:0" (Servo 1 to 0 deg), "S2:180" (Servo 2 to 180 deg)
    if (cmd.startsWith("S") && cmd.indexOf(':') != -1) {
      int colonIdx = cmd.indexOf(':');
      char servoChar = cmd.charAt(1); // '1' or '2'
      int angle = cmd.substring(colonIdx + 1).toInt();

      if (servoChar == '1') {
        servo1.write(angle);
      } else if (servoChar == '2') {
        servo2.write(angle);
      }
    }
  }
}
```

---

## 5. Comprehensive Error Handling Matrix

| Scenario | System State | Trigger Detection | Software Response | Recovery / Alert |
|---|---|---|---|---|
| **Serial Disconnect** | Loop active | `PySerial` write/read exception thrown | Captures exception, halts main thread, stops program | Emergency program termination. User manual reset. |
| **Belt Connection Dropped** | System sorting | `pydobot` write timeout / error | Captures exception, enters emergency state, halts | Logs critical error, attempts stop command, exits. |
| **Object Missed by Camera** | Cube passes IR1 | Mask returns 0 contours | Appends `"unknown"` to color queue | Prevents queue displacement. Cube runs to IR3 reject. |
| **Queue Overflow/Underflow** | IR2/IR3 fires with empty queue | Deque length is `0` | Discards physical event, logs warning | Pipeline misalignment alert. Continues next cycle. |
| **Servo Current Spike** | Servo sweeps | High battery draw / jitter | Isolated to external power rail ($6\text{V}$ battery) | Common ground guarantees logic safety; ESP32 unimpacted. |
