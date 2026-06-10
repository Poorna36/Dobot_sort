# Dobot Magician Color Sorting System
## Automated ML-Based Conveyor Belt Color Classifier

---

## Project Summary

A real-time color-based cube sorting system built on the Dobot Magician conveyor belt. A webcam captures cubes passing through a scan zone, a two-stage KNN→SVM machine learning classifier identifies the cube color, and ESP32-controlled servo motors physically divert cubes into color-coded bins. Unknown/unidentified objects trigger the Dobot robotic arm to remove them to a reject box.

---

## Team Context

- College AIML project
- 4-day build timeline
- Non-hardware-oriented team
- Uses college-owned Dobot Magician (non-invasive setup — no permanent modifications)

---

## Colors Handled

| Color | Servo Zone | Action |
|---|---|---|
| Green | IR2 zone — left servo | Pushed left into Green bin |
| Blue | IR2 zone — right servo | Pushed right into Blue bin |
| Yellow | IR3 zone — left servo | Pushed left into Yellow bin |
| Red | IR3 zone — right servo | Pushed right into Red bin |
| Unknown | IR3 zone — end of belt | Belt stops, arm removes to reject box |

---

## Hardware Overview

| Component | Role |
|---|---|
| Dobot Magician | Conveyor belt + robotic arm |
| Laptop | Entire backend — ML, logic, orchestration |
| ESP32 | Signal bridge — IR input, servo output |
| Logitech C270 Webcam | Single-shot image capture triggered by IR1 |
| 3x FC-51 IR Sensors | Cube detection at camera zone, pusher zone 1, pusher zone 2 |
| 4x SG90 Servo Motors | Physical cube pushers |
| 6V Battery (4xAA) | Powers servos via breadboard |
| Breadboard | Common ground + power distribution |

---

## Software Overview

| Component | Technology | Version | Role |
|---|---|---|---|
| Backend language | Python | 3.8+ | System orchestrator & ML execution |
| Computer vision | OpenCV (cv2) | 4.x | Bounding box detection & image cropping |
| ML models | scikit-learn | 1.x | KNN & SVM color classification |
| Model serialization | joblib | 1.x | Model persistence (.pkl format) |
| ESP32 communication | PySerial | 3.x | Reading IR sensor signals & sending servo sweep events |
| Dobot communication | pydobot | latest | Conveyor belt and arm API control |
| Queue system | collections.deque | stdlib | FIFO queuing for sequential sorting |
| Threading | threading | stdlib | Non-blocking execution & timed captures |

---

## ML Pipeline Overview

The system uses a robust 3-stage computer vision and machine learning pipeline to sort foam cubes:

1. **Stage 1: Cube Detection & Isolation**
   - The Logitech C270 camera frame is resized to 640×480 and converted to the HSV color space.
   - An HSV mask targeting high saturation (`S > 80` and `V > 60`) isolates the cube from the low-saturation backgrounds (belt, rails, cables, and walls).
   - Morphological opening removes small noise pixels.
   - The largest contour exceeding `5000` pixels is selected as the cube, and its bounding box (padded by 15px) is cropped.
2. **Stage 2: Feature Extraction**
   - The center 50% patch of the cropped cube is extracted to eliminate shadows, edge artifacts, and belt reflections.
   - Histograms for Hue (32 bins, 0–180), Saturation (32 bins, 0–256), and Value (32 bins, 0–256) channels are computed and normalized.
   - They are concatenated into a 96-dimensional feature vector representing the cube's exact color profile.
3. **Stage 3: Two-Stage Cascade Classification**
   - **Primary Classifier (KNN):** Checks the feature vector against the K-Nearest Neighbors (`k=3`) model. If the distance ratio of the nearest neighbor to the second-nearest neighbor is `< 0.7`, the KNN prediction is trusted and returned immediately.
   - **Fallback Classifier (SVM):** If KNN is ambiguous (ratio `>= 0.7`), the features are passed to a Support Vector Machine (RBF kernel) classifier. If SVM probability is `>= 0.6`, it returns the predicted class; otherwise, the cube is classified as `unknown`.

---

## Key Design Decisions

- **Laptop as brain** — all ML inference, logic, and orchestration on laptop. ESP32 is dumb signal bridge only.
- **Two-stage ML** — KNN for fast confident cases, SVM for ambiguous cases. Not deep learning — intentional choice for speed, explainability, and small dataset.
- **Queue-based sorting** — multiple cubes can be on belt simultaneously. Each cube's color is queued at IR1 and dequeued when it reaches its servo zone.
- **IR-triggered capture** — camera does not run continuously. One clean frame captured per cube, triggered by IR1 sensor.
- **Non-invasive hardware** — all components clip/sit on belt without permanent modification.

---

## Project Structure

```
dobot_color_sorter/
├── docs/
│   ├── README.md                        ← this file
│   ├── ARCHITECTURE_ELECTRICAL.md       ← wiring + power
│   ├── ARCHITECTURE_SOFTWARE.md         ← software pipeline
│   ├── ROBOT_DOCS.md                    ← Dobot specs + config
│   ├── INTEGRATION_DOCS.md              ← how all parts connect
│   ├── ESP32_FIRMWARE_DOCS.md           ← ESP32 firmware specs
│   ├── PHYSICAL_SETUP.md                ← physical layout & calibration
│   ├── ML_BACKEND.md                    ← ML model details (separate)
│   ├── CODE_LOGIC.md                    ← code logic details (separate)
│   └── DASHBOARD_WEBSITE.md             ← factory dashboard website (separate)
├── models/
│   ├── knn_model.pkl                    ← trained KNN
│   └── svm_model.pkl                    ← trained SVM
├── dataset/
│   ├── raw/                             ← 50 raw images per color
│   │   ├── green/
│   │   ├── blue/
│   │   ├── yellow/
│   │   └── red/
│   └── augmented/                       ← 250 augmented images per color
│       ├── green/
│       ├── blue/
│       ├── yellow/
│       └── red/
├── dashboard/
│   ├── index.html                       ← factory dashboard UI
│   ├── style.css                        ← custom vanilla CSS styling
│   └── app.js                           ← dynamic JS rendering & simulations
├── main.py                              ← entry point and orchestrator
├── classifier.py                        ← ML detection, features & classification
├── esp32_controller.py                  ← serial read/write to ESP32
├── dobot_controller.py                  ← belt + arm API wrapper
├── camera.py                            ← webcam image capture wrapper
├── augment.py                           ← dataset augmentation script
└── requirements.txt                     ← dependencies list
```


---

## Quick Start (Once Built)

```bash
pip install -r requirements.txt
python main.py
```

Ensure ESP32 is connected via USB, Dobot is connected via USB, and webcam is plugged in before running.

---

## Physical Setup Checklist

- [ ] Webcam mounted above belt scan zone, angled for clean top-down cube view
- [ ] IR Sensor 1 placed at camera scan zone
- [ ] IR Sensor 2 placed just before Green/Blue servo pair
- [ ] IR Sensor 3 placed just before Yellow/Red servo pair
- [ ] Green servo on left side of belt at IR2 zone
- [ ] Blue servo on right side of belt at IR2 zone
- [ ] Yellow servo on left side of belt at IR3 zone
- [ ] Red servo on right side of belt at IR3 zone
- [ ] Common ground connected on breadboard
- [ ] 6V battery connected to servo power rail
- [ ] ESP32 connected to laptop via USB
- [ ] Dobot connected to laptop via USB
- [ ] LED light positioned above scan zone for consistent lighting
