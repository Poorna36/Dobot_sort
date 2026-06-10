# ML Discussion Summary — Dobot Color Sorter
## For Opus: Generate ML_BACKEND.md, CODE_LOGIC.md, and edit existing docs

---

## Project Context

This is a college AIML project (4-day build) using a Dobot Magician conveyor belt to sort foam cubes by color. A webcam captures each cube, a Python ML pipeline classifies the color, and ESP32-controlled servos physically push cubes into bins.

**Colors:** Red, Green, Blue, Yellow (4 classes)  
**Unknown objects:** Arm removes to reject box  
**Dataset:** 50 real images per color → augmented to 250 per color (1000 total training images)

---

## Camera & Environment Reality (from actual images)

The Logitech C270 webcam produces low-quality, slightly washed-out frames (640×480).

**Background elements visible in frame:**
- Black conveyor belt surface (dominant foreground — low V in HSV)
- Dark grey/black belt rail (horizontal bar, left side)
- White/grey wall and door (background — low S in HSV)
- Robot arm machinery (right background — dark metal)
- Wooden floor (bottom right — warm brown, medium S)
- Cables and misc hardware (black — low V)

**Cube characteristics observed from real images:**
- Blue: clean, well-saturated cobalt blue — easiest to detect
- Red: IMPORTANT — appears as muted terracotta/brick orange-red, NOT clean red. Very desaturated compared to expected HSV red. Wraps around in hue (H ~0 and ~170).
- Green: moderate saturation, slightly muted olive-green
- Yellow: pale/cream yellow — low saturation, almost pastel. NOT vivid yellow.
- Cube fills approximately 30–45% of the frame
- Cube position in frame is NOT fixed — varies with belt position
- Camera is side-mounted (not top-down) — cube face is visible, not top

---

## Stage 1: Cube Detection / Isolation

**Method chosen: HSV High-Saturation Masking (no ML, fully deterministic)**

**Why this works:**
- Black belt → HSV V channel is low → masked out
- White/grey wall → HSV S channel is low → masked out  
- Dark cables/rail → low V → masked out
- Brown table/floor → moderate S, warm hue → partially filtered
- Cube colors → HIGH S, HIGH V → survives the mask

**Algorithm:**
```
1. Resize frame to 640×480 (normalize input)
2. Convert BGR → HSV
3. Apply threshold: S > 80 AND V > 60
   → This kills belt, wall, cables in one operation
4. Morphological cleanup: erode then dilate (kernel 5×5)
   → Removes noise pixels
5. Find all external contours
6. Filter contours: keep only those above min_area threshold (e.g. 5000 px²)
7. Select the LARGEST contour → this is the cube
8. Get bounding box of that contour → cv2.boundingRect()
9. Add padding (10–15px) to bounding box
10. Crop original frame to that bounding box
11. Pass cropped cube image to Stage 2
```

**Special handling for Red:**
Red hue wraps around in HSV (H=0–10 AND H=165–180 both = red).
The high-saturation mask does NOT care about hue — it only checks S and V — so the wrap-around is not a problem at the detection stage. It only matters during classification.

**Fallback if masking fails:**
If no contour found above min_area (cube not detected):
- Log warning
- Skip this frame
- Do not emit a classification result
- The IR sensor already confirmed a cube is present — retry once

---

## Stage 2: Feature Extraction

**Method: HSV Histogram of Center Patch**

**Why center patch:**
- Edges of cube have shadows, reflections from belt surface
- Top of cube has the ESP32/servo hardware sitting on it (visible in images)
- Center patch (middle 50% of the cropped bounding box) gives the cleanest color signal

**Algorithm:**
```
1. From cropped bounding box, compute center patch:
   x_start = width * 0.25
   x_end   = width * 0.75
   y_start = height * 0.25
   y_end   = height * 0.75
2. Convert patch to HSV
3. Compute histogram for each channel:
   - H channel: 32 bins, range 0–180
   - S channel: 32 bins, range 0–256
   - V channel: 32 bins, range 0–256
4. Concatenate: [H_hist, S_hist, V_hist] → 96-dimensional feature vector
5. Normalize: divide by total pixel count (so histograms sum to 1)
6. Return numpy array of shape (96,)
```

**Why 96 features:**
32 bins × 3 channels = 96. Enough to distinguish 4 well-separated colors.
Fine-grained enough for muted colors (terracotta red, cream yellow).

---

## Stage 3: Classification

**Two-stage cascade: KNN → SVM fallback**

### Primary: KNN (K-Nearest Neighbors)
- **k = 3** (odd number to avoid ties, small enough for 4 classes)
- **Distance metric:** Euclidean on normalized 96-dim HSV histogram
- **Confidence measure:** ratio of nearest neighbor distance to 2nd nearest
  - If ratio < threshold (e.g. 0.7): confident → use KNN result
  - If ratio ≥ threshold: ambiguous → pass to SVM
- **Why KNN first:** instant inference, no hyperparameter tuning, very interpretable

### Fallback: SVM (Support Vector Machine)
- **Kernel:** RBF (Radial Basis Function) — handles nonlinear color boundaries
- **C:** 10 (moderate regularization)
- **gamma:** 'scale' (auto from sklearn)
- **Decision function:** use predict_proba (with probability=True)
  - If max probability < 0.6: classify as UNKNOWN
  - If max probability ≥ 0.6: use predicted class
- **Why SVM fallback:** better margin maximization for ambiguous cases (terracotta red vs cream yellow under poor lighting)

### Unknown Handling
- If SVM probability < 0.6: result = "unknown"
- Unknown triggers: belt stops, Dobot arm removes object to reject box
- Unknown class has NO training data — it's detected purely by low confidence threshold, not a trained class

### Inference Pipeline (per cube):
```python
features = extract_hsv_histogram(cropped_patch)  # shape: (96,)

# Stage 1: KNN
knn_pred, knn_confidence = knn_predict(features)
if knn_confidence >= KNN_CONFIDENCE_THRESHOLD:
    return knn_pred

# Stage 2: SVM fallback
svm_pred, svm_proba = svm_predict(features)
if max(svm_proba) < SVM_PROBA_THRESHOLD:
    return "unknown"
return svm_pred
```

---

## Training Data & Augmentation

**Raw dataset:** 50 real images per color (200 total)  
**Target:** 250 images per color (1000 total)  
**Augmentations applied (5× per image):**

| Augmentation | Parameters | Purpose |
|---|---|---|
| Gaussian blur | kernel 3–7, random | Defocus simulation |
| Motion blur | horizontal kernel 9–15 | Belt movement simulation |
| Brightness shift | ±20–40 on HSV V channel ONLY | Lighting variation |
| Slight rotation | ±5–10 degrees | Cube angle variation |
| Random crop + resize | Keep 80–90% of frame | Distance/position variation |

**Critical: Color jitter / hue shift is NOT used** — color IS the classification label. Shifting hue would corrupt ground truth.

**Folder structure:**
```
dataset/
├── raw/
│   ├── blue/       (50 images)
│   ├── red/        (50 images)
│   ├── green/      (50 images)
│   └── yellow/     (50 images)
└── augmented/
    ├── blue/       (250 images)
    ├── red/        (250 images)
    ├── green/      (250 images)
    └── yellow/     (250 images)
```

**Training note on red:** The red cube appears terracotta/brick in real camera images — NOT clean HSV red. Training MUST use real camera captures, not synthetic clean-red images. The augmented dataset preserves this real-camera color profile.

---

## Libraries Used

| Library | Version | Role |
|---|---|---|
| opencv-python | ≥4.5 | HSV conversion, masking, contours, crop |
| numpy | ≥1.21 | Feature vectors, histogram computation |
| scikit-learn | ≥1.0 | KNN, SVM, train/test split, metrics |
| joblib | ≥1.0 | Save/load .pkl model files |

No deep learning. No GPU required. All inference runs on the laptop CPU in real time.

---

## Files To Generate / Edit

### New files to CREATE:

**1. `docs/ML_BACKEND.md`**
Full ML documentation covering:
- Detection approach (HSV masking) with exact parameters
- Feature extraction (HSV histogram, center patch, 96 dims)
- KNN architecture, k=3, confidence thresholding
- SVM architecture, RBF kernel, probability fallback
- Unknown detection via threshold (no unknown training class)
- Training procedure and dataset structure
- Model persistence (.pkl files)
- Accuracy expectations per color

**2. `docs/CODE_LOGIC.md`**
Code-level logic documentation covering:
- `classifier.py` — full function breakdown
  - `detect_cube(frame)` → bounding box
  - `extract_features(crop)` → 96-dim vector
  - `classify(features)` → color string
  - `train(dataset_path)` → saves .pkl models
- `camera.py` — capture trigger logic (IR1 fires → single frame capture)
- `main.py` — orchestration loop
- Queue system: how color is stored at IR1 and dequeued at IR2/IR3
- Threading: Timer-based delays between IR zones
- Error handling: what happens if detection fails, serial drops, etc.

### Existing files to EDIT:

**3. `docs/README.md`**
Add a section: "ML Pipeline Overview" summarizing the 3-stage approach (detect → extract → classify). Update the Software Overview table to include joblib. Confirm the dataset/ folder structure matches what's documented here.

**4. `docs/ARCHITECTURE_SOFTWARE.md`**
Add detail to the ML section: replace any placeholder ML description with the actual HSV masking + KNN/SVM approach. Add a data flow diagram in ASCII if not present.

---

## Key Design Decisions Summary (for Opus context)

1. **No deep learning** — intentional. 4 colors, controlled environment, small dataset, 4-day build. HSV + KNN/SVM is the correct tool.

2. **HSV over RGB** — RGB mixes brightness into color values. HSV separates hue (color) from saturation and value (lighting). Critical for handling lighting variation.

3. **Center patch only** — edges have shadows and reflections. Center is clean color.

4. **KNN before SVM** — KNN is faster and simpler. Only escalate to SVM when KNN is uncertain.

5. **Unknown by threshold, not class** — no unknown training data needed. Anything the model isn't confident about becomes unknown.

6. **Augmentation preserves color** — only geometric and brightness augments. No hue/saturation shifts ever.

7. **Deterministic detection** — HSV masking has no randomness, no model weights to go wrong. If detection fails, it fails obviously (no contour found). Easy to debug.
