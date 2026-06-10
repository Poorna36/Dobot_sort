# Data Augmentation Plan
## Dobot Color Sorter — 50 → 250 Images Per Color

---

## Goal

Expand raw dataset from 50 real images per color to 250 per color.
Total: 200 raw → 1000 augmented training images.

Each original image produces exactly 5 augmented variants.

---

## Critical Rule

**NEVER augment hue or saturation.**
Color IS the label. Any hue/saturation shift corrupts ground truth.
Only geometric transforms and brightness (V channel only) are allowed.

---

## Augmentations (5 per image)

### Augment 1 — Gaussian Blur
**Simulates:** slight defocus, camera shake, low sharpness (C270 is a low-quality webcam)

```python
kernel_size = random.choice([3, 5, 7])
augmented = cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)
```

Parameters:
- Kernel size: 3, 5, or 7 (randomly chosen per image)
- Sigma: 0 (auto from kernel size)

---

### Augment 2 — Motion Blur (Horizontal)
**Simulates:** cube moving on belt during capture, slight camera-cube relative motion

```python
kernel_size = random.randint(9, 15)
kernel = np.zeros((kernel_size, kernel_size))
kernel[kernel_size // 2, :] = 1.0 / kernel_size
augmented = cv2.filter2D(image, -1, kernel)
```

Parameters:
- Kernel size: 9–15 (horizontal only — belt moves horizontally)
- Direction: horizontal axis only

---

### Augment 3 — Brightness Shift (V channel only)
**Simulates:** slight lighting variation, overhead light intensity change

```python
hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.int32)
delta = random.randint(-40, 40)
hsv[:, :, 2] = np.clip(hsv[:, :, 2] + delta, 0, 255)
augmented = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
```

Parameters:
- V channel delta: ±20 to ±40 (randomly chosen)
- H and S channels: unchanged (critical — color must not shift)
- Clipped to [0, 255]

---

### Augment 4 — Slight Rotation
**Simulates:** cube not perfectly square to camera, slight placement angle

```python
angle = random.uniform(-10, 10)
h, w = image.shape[:2]
M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
augmented = cv2.warpAffine(image, M, (w, h),
                            borderMode=cv2.BORDER_REFLECT)
```

Parameters:
- Rotation: ±5 to ±10 degrees (randomly chosen)
- Border fill: BORDER_REFLECT (mirrors edge pixels — avoids black borders)
- No scale change

---

### Augment 5 — Random Crop + Resize
**Simulates:** cube appearing closer or farther from camera, position variation in frame

```python
h, w = image.shape[:2]
crop_factor = random.uniform(0.80, 0.90)
crop_h = int(h * crop_factor)
crop_w = int(w * crop_factor)
x = random.randint(0, w - crop_w)
y = random.randint(0, h - crop_h)
cropped = image[y:y+crop_h, x:x+crop_w]
augmented = cv2.resize(cropped, (w, h))
```

Parameters:
- Crop factor: 80–90% of original dimensions
- Position: random origin within valid range
- Resize back to original dimensions after crop

---

## Augmentations NOT Used (and why)

| Augmentation | Reason Excluded |
|---|---|
| Hue shift | Color IS the label — would corrupt ground truth |
| Saturation change | Affects color perception — not safe |
| Vertical flip | Physically impossible — cube never upside down on belt |
| Heavy rotation (>15°) | Unrealistic — cube is always roughly upright |
| Color jitter | Same as hue/saturation — corrupts label |
| Grayscale | Destroys color information — useless for color classifier |

---

## Optional Additions (if accuracy needs improvement)

| Augmentation | Parameters | When to add |
|---|---|---|
| Horizontal flip | Mirror left-right | Safe — cube is symmetric. Add if underfitting. |
| Gaussian noise | mean=0, std=5–15 on pixel values | Camera noise simulation. Add if model overfits. |
| JPEG compression artifact | quality 60–80 | Simulates webcam compression. Low priority. |

---

## Output Folder Structure

```
dataset/
├── raw/
│   ├── blue/       ← 50 images (original captures)
│   ├── red/        ← 50 images
│   ├── green/      ← 50 images
│   └── yellow/     ← 50 images
└── augmented/
    ├── blue/       ← 250 images (50 originals + 200 augmented)
    ├── red/        ← 250 images
    ├── green/      ← 250 images
    └── yellow/     ← 250 images
```

**Naming convention:**
```
original:   blue_001.jpg
augmented:  blue_001_aug1.jpg  (gaussian blur)
            blue_001_aug2.jpg  (motion blur)
            blue_001_aug3.jpg  (brightness)
            blue_001_aug4.jpg  (rotation)
            blue_001_aug5.jpg  (crop+resize)
```

---

## Script Usage (augment.py)

```bash
python augment.py --input dataset/raw --output dataset/augmented
```

Processes all 4 color folders automatically.
Saves originals + 5 augments per image into output folder.
Prints count summary on completion.

---

## Expected Training Data Quality Notes

- **Red cube:** Real images show terracotta/brick tone — NOT clean red. Augmentation preserves this. Do not replace with cleaner red images — train on what the camera sees.
- **Yellow cube:** Appears pale/cream in real images — low saturation. Brightness augmentation (aug3) is especially important for yellow to cover the dim/bright range.
- **Blue cube:** Clean and saturated — easiest. All augments are safe.
- **Green cube:** Moderately saturated olive-green. All augments are safe.
