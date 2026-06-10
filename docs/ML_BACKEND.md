# Machine Learning Backend Documentation
## Dobot Color Sorter — Dynamic CV & ML Pipeline Specification

This document provides a fully detailed and mathematically rigorous specification of the machine learning and computer vision pipeline. All coordinates, constants, threshold values, and algorithms are defined here to ensure exact reproducibility in the codebase.

---

## 1. Stage 1: Cube Detection & Isolation

Instead of relying on hardcoded coordinates or manual region-of-interest (ROI) crops, the system dynamically locates the cube within the camera frame. This allows for variations in physical conveyor alignment and camera mount drift.

### 1.1 Resolution Normalization
- All raw frames captured from the Logitech C270 webcam are immediately resized to **640×480 pixels** using bilinear interpolation (`cv2.INTER_LINEAR`). This standardizes pixel-area calculations.

### 1.2 HSV Color Conversion
- The standardized BGR frame is converted to the HSV (Hue, Saturation, Value) color space:
  $$\text{HSV} = \text{cv2.cvtColor}(\text{frame}, \text{cv2.COLOR\_BGR2HSV})$$

### 1.3 High-Saturation / High-Value Masking
- The conveyor belt (black rubber) and background clutter (dark grey rails, white walls, shadows) are filtered out dynamically using a Saturation-Value threshold mask.
- Only pixels satisfying $S > 80$ (to eliminate white, grey, and black background components) and $V > 60$ (to eliminate shadows and dark cables) are kept.
- **Threshold bounds in OpenCV format:**
  - Lower Bound: `[0, 80, 60]`
  - Upper Bound: `[180, 255, 255]`
- **OpenCV Implementation:**
  ```python
  lower_bound = np.array([0, 80, 60], dtype=np.uint8)
  upper_bound = np.array([180, 255, 255], dtype=np.uint8)
  mask = cv2.inRange(hsv_frame, lower_bound, upper_bound)
  ```

### 1.4 Morphological Cleanup
- To remove single-pixel camera sensor noise and small stray reflections:
  1. Morphological opening is applied using a flat, square $5\times5$ structuring element (kernel) of ones.
  2. This is implemented via an erosion step followed by a dilation step:
     ```python
     kernel = np.ones((5, 5), dtype=np.uint8)
     cleaned_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
     ```

### 1.5 Contour Analysis & Filter
- The system extracts external contours from the cleaned binary mask:
  ```python
  contours, _ = cv2.findContours(cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
  ```
- **Area Constraint:** Any contour whose area is less than or equal to $5000 \text{ px}^2$ is discarded. This eliminates background details that bleed past the mask (e.g. warm wood grain on the floor).
- **Largest Selection:** The largest remaining contour is identified as the cube.
  ```python
  valid_contours = [c for c in contours if cv2.contourArea(c) > 5000]
  if not valid_contours:
      # Detection failed - skip frame
      return None
  largest_contour = max(valid_contours, key=cv2.contourArea)
  ```

### 1.6 Bounding Box & Padding
- The bounding box for the largest contour is calculated:
  $$x, y, w, h = \text{cv2.boundingRect}(\text{largest\_contour})$$
- A safety padding of **15 pixels** is added to all four directions to prevent clipping the outer edges of the cube.
- The coordinates are clamped to the $640\times480$ frame boundaries:
  ```python
  padding = 15
  x1 = max(0, x - padding)
  y1 = max(0, y - padding)
  x2 = min(640, x + w + padding)
  y2 = min(480, y + h + padding)
  cropped_cube = frame[y1:y2, x1:x2]
  ```

---

## 2. Stage 2: Feature Extraction

The cropped cube image contains edge shadows, conveyor belt background bleed, and potentially reflection artifacts from the overhead lighting or physical brackets holding the camera. To extract the cleanest color profile, the system extracts a center patch.

### 2.1 Center Patch Crop
- From the cropped cube image (width $w_c$, height $h_c$), only the middle 50% section along both axes is kept.
- **Center patch coordinates:**
  $$x_{\text{start}} = \text{int}(w_c \times 0.25), \quad x_{\text{end}} = \text{int}(w_c \times 0.75)$$
  $$y_{\text{start}} = \text{int}(h_c \times 0.25), \quad y_{\text{end}} = \text{int}(h_c \times 0.75)$$
  ```python
  hc, wc = cropped_cube.shape[:2]
  center_patch = cropped_cube[int(hc * 0.25):int(hc * 0.75), int(wc * 0.25):int(wc * 0.75)]
  ```

### 2.2 HSV Histogram Computation
- The center patch BGR image is converted to HSV.
- Histograms are calculated individually for each channel with **32 bins** per channel:
  - **H Channel:** 32 bins, range $[0, 180]$
  - **S Channel:** 32 bins, range $[0, 256]$
  - **V Channel:** 32 bins, range $[0, 256]$
- **OpenCV Implementation:**
  ```python
  patch_hsv = cv2.cvtColor(center_patch, cv2.COLOR_BGR2HSV)
  hist_h = cv2.calcHist([patch_hsv], [0], None, [32], [0, 180])
  hist_s = cv2.calcHist([patch_hsv], [1], None, [32], [0, 256])
  hist_v = cv2.calcHist([patch_hsv], [2], None, [32], [0, 256])
  ```

### 2.3 Normalization & Concatenation
- Each histogram is normalized by dividing by the sum of its bins plus an epsilon constant ($1\times10^{-7}$) to prevent division-by-zero errors. This ensures each channel's histogram integrates to 1.0, making the features invariant to the absolute surface area of the patch.
- The three normalized 32-bin vectors are concatenated into a single **96-dimensional feature vector**:
  ```python
  hist_h /= (np.sum(hist_h) + 1e-7)
  hist_s /= (np.sum(hist_s) + 1e-7)
  hist_v /= (np.sum(hist_v) + 1e-7)
  feature_vector = np.concatenate([hist_h.flatten(), hist_s.flatten(), hist_v.flatten()])
  ```

---

## 3. Stage 3: Two-Stage Classification Cascade

The classification relies on a two-stage fallback cascade. KNN provides fast, deterministic, local neighborhood checks. SVM (RBF) acts as a high-margin decision surface for border cases.

```
                  ┌────────────────────────┐
                  │ 96-Dim Feature Vector  │
                  └───────────┬────────────┘
                              ▼
                 ┌──────────────────────────┐
                 │ Stage 1: KNN (k=3)       │
                 │ Distance Ratio Test      │
                 └────────────┬─────────────┘
                              │
                 Ratio < 0.7? │
                      ┌───────┴───────┐
                  YES │            NO │
                      ▼               ▼
                 ┌──────────┐   ┌──────────────────────────┐
                 │ KNN Pred │   │ Stage 2: SVM (RBF)       │
                 └──────────┘   │ Probability Check        │
                                └─────────────┬────────────┘
                                              │
                                   Prob >= 0.6?
                                      ┌───────┴───────┐
                                  YES │            NO │
                                      ▼               ▼
                                 ┌──────────┐   ┌───────────┐
                                 │ SVM Pred │   │  UNKNOWN  │
                                 └──────────┘   └───────────┘
```

### 3.1 Primary Classifier: K-Nearest Neighbors (KNN)
- **Parameters:** $k = 3$, Distance Metric = Euclidean.
- **Confidence Metric (Lowe's Distance Ratio Test):**
  - We retrieve the distance to the nearest neighbor ($d_1$) and the distance to the second nearest neighbor ($d_2$) using `knn.kneighbors()`.
  - The ratio is calculated:
    $$\text{ratio} = \frac{d_1}{d_2 + 1\times10^{-7}}$$
  - If $\text{ratio} < 0.7$, the nearest neighbor is significantly closer than any secondary neighbor, indicating a confident match. The prediction of the KNN model is returned immediately.
  - If $\text{ratio} \ge 0.7$, the neighbors are clustered closely together, indicating ambiguity. The features are escalated to Stage 2.

### 3.2 Fallback Classifier: Support Vector Machine (SVM)
- **Parameters:** Kernel = RBF (Radial Basis Function), $C = 10$, $\gamma = \text{'scale'}$, probability estimation enabled (`probability=True`).
- **Probability Threshold:**
  - The SVM calculates class probabilities for the 4 target classes: `['green', 'blue', 'yellow', 'red']`.
  - The maximum class probability is evaluated:
    $$p_{\text{max}} = \max(\text{predict\_proba}(\mathbf{x}))$$
  - If $p_{\text{max}} \ge 0.6$, the corresponding class label is returned.
  - If $p_{\text{max}} < 0.6$, the object is classified as **"unknown"**.

### 3.3 Unknown Handling Philosophy
- There is **no training data** for the "unknown" class. An object is classified as unknown purely by failing the confidence criteria of both stage-1 (KNN ratio test) and stage-2 (SVM probability threshold). This catches foreign objects, flipped cubes, or severe lighting changes.

---

## 4. Dataset & Augmentation Strategy

To train the models to handle camera artifacts, motion blur, and light shifts, a strict augmentation protocol expands the raw dataset from **50 to 250 images per color** (total 1,000 training images).

### 4.1 Critical Color Ground-Truth Rule
> [!IMPORTANT]
> **Never shift hue or saturation.**
> Because color is the exact target label, any shift in Hue or Saturation values will alter the ground truth. Only changes to geometric parameters and brightness (Value channel only) are permitted.

### 4.2 Augmentation Functions (5 per original image)

| Variant | Augmentation | OpenCV C++ / Python Logic | Parameters |
|---|---|---|---|
| **Aug 1** | Gaussian Blur | `cv2.GaussianBlur(img, (k_sz, k_sz), 0)` | $k_{\text{sz}} \in \{3, 5, 7\}$ (random) |
| **Aug 2** | Motion Blur | `cv2.filter2D(img, -1, h_kernel)` | Horizontal kernel of size $9 \text{ to } 15$ pixels |
| **Aug 3** | Brightness Shift | `hsv[:,:,2] = np.clip(hsv[:,:,2] + delta, 0, 255)` | $\delta \in [-40, 40]$ (V channel only) |
| **Aug 4** | Slight Rotation | `cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)` | Angle $\theta \in [-10^\circ, 10^\circ]$ |
| **Aug 5** | Crop + Resize | `img[y:y+ch, x:x+cw]` then resize back to original | Crop size = $80\% \text{ to } 90\%$ of frame |

### 4.3 Target Class Characteristics (Webcam Reality)
- **Blue Cube:** Saturated cobalt blue. Easy to classify; yields high HSV Saturation.
- **Green Cube:** Muted, moderate-saturation olive green.
- **Yellow Cube:** Pale, low-saturation cream-yellow. Easy to confuse with light grey backgrounds; value shifts (Aug 3) are critical to cover light fluctuations.
- **Red Cube:** Muted brick/terracotta orange-red. The Hue channel wraps around in HSV ($H \approx [0, 10]$ and $H \approx [165, 180]$). The dynamic S-V detection mask handles this without issues, while the 32-bin Hue histogram correctly maps both wrap-around sectors.

---

## 5. Model Serialization & Persistence

- The classifiers are trained offline on the laptop CPU using the augmented dataset.
- Models are persisted as binary files using `joblib` (version $\ge 1.0.0$) inside the `models/` directory:
  - `models/knn_model.pkl`
  - `models/svm_model.pkl`
- The model files must contain the fully fitted scikit-learn estimator objects (`KNeighborsClassifier` and `SVC`) so they can be loaded instantly during startup:
  ```python
  import joblib
  knn = joblib.load("models/knn_model.pkl")
  svm = joblib.load("models/svm_model.pkl")
  ```
