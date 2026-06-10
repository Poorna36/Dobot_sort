# Project Build Order Checklist
## Dobot Color Sorter — Step-by-Step Implementation Roadmap

Follow this order of operations to implement, calibrate, and verify the conveyor belt sorting system. Check off each box as you complete the corresponding step.

---

## Phase 1: Data Acquisition & Model Training

### 1.1 Dataset Setup
- [x] Create the data directories on disk:
  - `dataset/raw/green/`, `dataset/raw/blue/`, `dataset/raw/yellow/`, `dataset/raw/red/`
  - `dataset/augmented/green/`, `dataset/augmented/blue/`, `dataset/augmented/yellow/`, `dataset/augmented/red/`
- [x] Connect your Logitech C270 webcam and capture **50 raw images** for each color class. Save them inside the corresponding `dataset/raw/{color}/` folders.
  * **Tip:** Capture cubes under different angles and center positions in the webcam field of view to teach the model variance.

### 1.2 Data Augmentation
- [x] Write the dataset augmenter script `augment.py` implementing the geometric and value shifts defined in [ML_BACKEND.md Section 4](file:///c:/Workspace/code/projects/dobot_sort/docs/ML_BACKEND.md#L131-L158).
- [x] Execute the augmentation pipeline:
  ```bash
  python augment.py --input dataset/raw --output dataset/augmented
  ```
- [x] Verify that `dataset/augmented/` contains exactly **250 images** per color (1,000 total files, with suffix `_aug1.jpg` to `_aug5.jpg`).

### 1.3 Model Training & Verification
- [x] Implement the `train_models(dataset_path, output_knn, output_svm)` function inside `classifier.py` as detailed in [CODE_LOGIC.md Section 3.2](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L124-L260).
- [x] Run the offline model compiler script:
  ```bash
  python -c "from classifier import train_models; train_models('dataset', 'models/knn_model.pkl', 'models/svm_model.pkl')"
  ```
- [x] Verify that `models/knn_model.pkl` and `models/svm_model.pkl` files are created.
- [x] Write a short validation script to print model accuracy scores, cross-validation metrics, and verify that ambiguous color margins are cleanly split by the fallback boundary.

---

## Phase 2: Logic Coding & Software Integrity

### 2.1 Backend Software Modules
- [x] Populate [config.py](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L86-L122) with basic communication ports, speed settings, and default coordinates.
- [x] Populate [classifier.py](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L124-L260) with dynamic HSV masking, feature extraction, and KNN-SVM cascade prediction logic.
- [x] Populate [camera.py](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L262-L281) with webcam VideoCapture logic.
- [x] Populate [esp32_controller.py](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L283-L319) with Pyserial readline and command transmitter logic.
- [x] Populate [dobot_controller.py](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L321-L402) with conveyor control and vacuum pickup sequences.
- [x] Populate [main.py](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L404-L525) with thread loops, queue logic, and `threading.Timer` camera capture deferrals.

### 2.2 Integrity & Stand-Alone Runs
- [x] Run syntax checks and resolve import statement warnings:
  ```bash
  python -m py_compile main.py classifier.py camera.py esp32_controller.py dobot_controller.py
  ```
- [x] Mock local tests: Run `main.py` without hardware connected (e.g. comment out serial and Dobot connection wrappers in `config.py` temporarily) and print queue updates to verify FIFO queue synchronization.

---

## Phase 3: Dashboard Web Interface

### 3.1 Web UI Layout & Style
- [x] Create the `dashboard/` directory.
- [x] Write `dashboard/index.html` (scaffold container panels: live scanner viewport, stats lists, FIFO queue bar, and terminal log buffer).
- [x] Write `dashboard/style.css` (implement dark SCADA layout theme, glassmorphism shadows, HSL color indicators, and keyframe scanning laser animations).

### 3.2 Simulation Logic & Client-Side Hooks
- [x] Write `dashboard/app.js` containing the local mock animation loops (translating/drawing cubes on the conveyor belt, bounding box targets, queue insertions, log prints).
- [x] Open `dashboard/index.html` in Chrome/Firefox. Click **"Place Mock Cube"** and check visual responsiveness, queues, and counts.
- [x] Hook up the local WebSocket listener loop in `app.js` to wait for backend telemetry broadcasts.

---

## Phase 4: Hardware Assembly & Final Integration

### 4.1 Microcontroller Setup
- [ ] Install the Arduino IDE and load the **`ESP32Servo`** library.
- [ ] Copy and paste the C++ firmware from [CODE_LOGIC.md Section 4](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L527-L670) and flash it onto the ESP32.
- [ ] Test via Serial Monitor: block the IR sensors and type servo triggers (`SG`, `SB`, `SY`, `SR`) to verify that the ESP32 responds correctly.

### 4.2 Physical Mounting & Calibration
- [ ] Mount the webcam above the scan zone (~25cm high). Mount IR Sensor 1 so the light beam intersects passing cubes.
- [ ] Place IR Sensor 2 and Servo Pair 1 (Green/Blue) at the first zone.
- [ ] Place IR Sensor 3 and Servo Pair 2 (Yellow/Red) at the second zone.
- [ ] **Unified Grounds:** Connect the ESP32 GND and the 6V servo battery GND on the breadboard.
- [ ] **Sensor Sensitivity:** Calibrate the blue potentiometers on the three FC-51 boards until cubes trigger the indicator LEDs cleanly but the black conveyor belt does not.
- [ ] **Dobot Calibration:** Jog the Dobot arm using Dobot Studio. Align the vacuum suction cup over the pickup zone at the end of the belt and above the reject box. Copy the exact coordinate floats into [config.py](file:///c:/Workspace/code/projects/dobot_sort/docs/CODE_LOGIC.md#L86-L122).

### 4.3 End-to-End Integration Run
- [ ] Plug all USB connections (ESP32, Dobot, webcam) into the laptop.
- [ ] Power on the 6V AA servo battery pack.
- [ ] Start the orchestrator:
  ```bash
  python main.py
  ```
- [ ] Feed test cubes of each color through the conveyor belt and verify they are successfully classified, queued, tracked, and physically pushed into their correct bins!
