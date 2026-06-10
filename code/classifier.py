# classifier.py
# Dobot Color Sorter — ML Detection, Feature Extraction & Classification
#
# Three pipeline stages:
#   Stage 1 — detect_cube()      : HSV mask → contour → padded bounding box crop
#   Stage 2 — extract_features() : center 50% patch → 96-dim normalized HSV histogram
#   Stage 3 — TwoStageClassifier : KNN ratio test → SVM probability fallback
#
# Also contains train_models() for offline model compilation.

import cv2
import numpy as np
import os
import joblib
import logging
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 1: Cube Detection via Dynamic HSV Masking
# ---------------------------------------------------------------------------

def detect_cube(frame):
    """
    Locates the foam cube in a raw BGR camera frame using high-saturation/value
    HSV masking. Does NOT rely on a fixed ROI — position-invariant.

    Parameters
    ----------
    frame : np.ndarray
        Raw BGR image from cv2.VideoCapture.

    Returns
    -------
    cropped_cube : np.ndarray or None
        BGR crop of the detected cube (padded bounding box).
        None if no valid cube contour is found.
    bbox : tuple (x1, y1, x2, y2) or None
        Pixel coordinates of the padded bounding box in the 640×480 frame.
        None if detection failed.
    """
    # Step 1: Normalize frame size
    frame = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)

    # Step 2: Convert BGR → HSV
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Step 3: High-saturation / high-value mask
    #   S > 80  eliminates: black belt, white walls, grey rails (low saturation)
    #   V > 60  eliminates: shadows, dark cables (low brightness)
    #   H: full 0–180 range — no hue filter, handles red's wrap-around naturally
    lower_bound = np.array([0,  80,  60], dtype=np.uint8)
    upper_bound = np.array([180, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_bound, upper_bound)

    # Step 4: Morphological opening — erode then dilate (5×5 kernel)
    #   Removes isolated noise pixels that survive the saturation threshold
    kernel = np.ones((5, 5), dtype=np.uint8)
    cleaned_mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # Step 5: Find external contours on the cleaned binary mask
    contours, _ = cv2.findContours(
        cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # Step 6: Filter by minimum area — removes residual background bleed
    valid_contours = [c for c in contours if cv2.contourArea(c) > config.DETECTION_MIN_AREA]

    if not valid_contours:
        logger.warning("detect_cube: No valid contour found above min area %d px².",
                       config.DETECTION_MIN_AREA)
        return None, None

    # Step 7: Select largest contour — this is the cube
    largest_contour = max(valid_contours, key=cv2.contourArea)

    # Step 8: Get bounding rectangle and apply padding
    x, y, w, h = cv2.boundingRect(largest_contour)
    p = config.DETECTION_PADDING
    x1 = max(0,   x - p)
    y1 = max(0,   y - p)
    x2 = min(640, x + w + p)
    y2 = min(480, y + h + p)

    # Step 9: Crop original (BGR) frame to padded bounding box
    cropped_cube = frame[y1:y2, x1:x2]

    if cropped_cube.size == 0:
        logger.warning("detect_cube: Bounding box crop produced empty image.")
        return None, None

    return cropped_cube, (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# Stage 2: Feature Extraction — 96-dim Normalized HSV Histogram
# ---------------------------------------------------------------------------

def extract_features(cropped_cube):
    """
    Extracts a 96-dimensional normalized HSV histogram from the center 50%
    patch of the cropped cube image.

    Using center 50% avoids:
      - Edge shadows cast by the belt rails
      - Reflections from overhead LED lighting on the cube's outer edges

    Parameters
    ----------
    cropped_cube : np.ndarray
        BGR crop returned by detect_cube().

    Returns
    -------
    feature_vector : np.ndarray, shape (96,)
        Concatenation of normalized H (32 bins), S (32 bins), V (32 bins)
        histograms. Sums to ~3.0 (each channel sums to ~1.0).
    """
    hc, wc = cropped_cube.shape[:2]

    # Center 50% patch (25%–75% of each dimension)
    ys = int(hc * 0.25)
    ye = int(hc * 0.75)
    xs = int(wc * 0.25)
    xe = int(wc * 0.75)
    center_patch = cropped_cube[ys:ye, xs:xe]

    # Convert to HSV for hue-based color discrimination
    patch_hsv = cv2.cvtColor(center_patch, cv2.COLOR_BGR2HSV)

    # Compute per-channel histograms
    hist_h = cv2.calcHist([patch_hsv], [0], None, [32], [0, 180])   # Hue
    hist_s = cv2.calcHist([patch_hsv], [1], None, [32], [0, 256])   # Saturation
    hist_v = cv2.calcHist([patch_hsv], [2], None, [32], [0, 256])   # Value

    # Normalize each histogram so it sums to 1 (pixel-count invariant)
    hist_h /= (np.sum(hist_h) + 1e-7)
    hist_s /= (np.sum(hist_s) + 1e-7)
    hist_v /= (np.sum(hist_v) + 1e-7)

    # Concatenate → 32 + 32 + 32 = 96-dimensional feature vector
    feature_vector = np.concatenate([
        hist_h.flatten(),
        hist_s.flatten(),
        hist_v.flatten()
    ])
    return feature_vector


# ---------------------------------------------------------------------------
# Stage 3: Two-Stage Classification Cascade
# ---------------------------------------------------------------------------

class TwoStageClassifier:
    """
    Loads pre-trained KNN and SVM models from .pkl files and runs them in
    a confidence-gated cascade:

      1. KNN (k=3): Compute Lowe's distance ratio (d1/d2).
         If ratio < KNN_RATIO_THRESHOLD → confident → return KNN label.
      2. SVM (RBF, C=10): If KNN is ambiguous → run SVM.
         If max probability >= SVM_PROBA_THRESHOLD → return SVM label.
         Else → return "unknown".
    """

    def __init__(self, knn_path='models/knn_model.pkl',
                 svm_path='models/svm_model.pkl'):
        if not os.path.isfile(knn_path):
            raise FileNotFoundError(f"KNN model not found: {knn_path}")
        if not os.path.isfile(svm_path):
            raise FileNotFoundError(f"SVM model not found: {svm_path}")

        self.knn = joblib.load(knn_path)
        self.svm = joblib.load(svm_path)
        logger.info("TwoStageClassifier: models loaded from '%s' and '%s'.",
                    knn_path, svm_path)

    def classify(self, feature_vector):
        """
        Run the KNN → SVM cascade on a 96-dim feature vector.

        Parameters
        ----------
        feature_vector : np.ndarray, shape (96,)

        Returns
        -------
        label      : str   — 'green', 'blue', 'yellow', 'red', or 'unknown'
        confidence : float — pseudo-confidence score in [0.0, 1.0]
        model_used : str   — 'KNN', 'SVM', or 'SVM_REJECT'
        """
        features = feature_vector.reshape(1, -1)

        # Stage 1: KNN (k=3) — distance ratio test
        distances, _ = self.knn.kneighbors(features)
        d1 = distances[0][0]
        d2 = distances[0][1]
        ratio = d1 / (d2 + 1e-7)

        if ratio < config.KNN_RATIO_THRESHOLD:
            label = self.knn.predict(features)[0]
            # Map ratio to confidence: ratio 0.0 → confidence 1.0
            confidence = float(np.clip(1.0 - ratio, 0.0, 1.0))
            logger.debug("KNN: %s (ratio=%.3f, conf=%.3f)", label, ratio, confidence)
            return label, confidence, 'KNN'

        # Stage 2: SVM (RBF) fallback
        svm_proba = self.svm.predict_proba(features)[0]
        max_idx  = int(np.argmax(svm_proba))
        max_prob = float(svm_proba[max_idx])

        if max_prob >= config.SVM_PROBA_THRESHOLD:
            label = self.svm.classes_[max_idx]
            logger.debug("SVM: %s (prob=%.3f)", label, max_prob)
            return label, max_prob, 'SVM'

        logger.debug("SVM_REJECT: max_prob=%.3f below threshold.", max_prob)
        return 'unknown', max_prob, 'SVM_REJECT'


# ---------------------------------------------------------------------------
# Offline Training Utility
# ---------------------------------------------------------------------------

def _load_dataset(dataset_path):
    """
    Walks dataset/augmented/{color}/ and extracts feature vectors for each image.

    Returns
    -------
    X : np.ndarray, shape (N, 96)
    y : np.ndarray, shape (N,)  — string labels
    """
    X, y = [], []

    for label in config.CLASSES:
        label_dir = os.path.join(dataset_path, 'augmented', label)
        if not os.path.isdir(label_dir):
            logger.warning("Training: folder not found — %s", label_dir)
            continue

        image_files = [
            f for f in os.listdir(label_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ]

        if not image_files:
            logger.warning("Training: no images in %s", label_dir)
            continue

        print(f"  Loading [{label.upper()}] — {len(image_files)} images...")

        for filename in image_files:
            img_path = os.path.join(label_dir, filename)
            img = cv2.imread(img_path)
            if img is None:
                logger.warning("  Skipping unreadable file: %s", img_path)
                continue

            cropped, _ = detect_cube(img)
            if cropped is None:
                # Detection failed on training image — skip
                # This is acceptable: augmented border images may not survive mask
                logger.warning("  No cube detected in training image: %s", filename)
                continue

            feat = extract_features(cropped)
            X.append(feat)
            y.append(label)

    return np.array(X), np.array(y)


def train_models(dataset_path='.',
                 knn_output='models/knn_model.pkl',
                 svm_output='models/svm_model.pkl'):
    """
    Full offline training pipeline. Loads augmented dataset, trains KNN and SVM,
    prints accuracy metrics, and saves .pkl files.

    Parameters
    ----------
    dataset_path : str
        Root path containing the dataset/ directory.
    knn_output : str
        Destination path for the serialized KNN model.
    svm_output : str
        Destination path for the serialized SVM model.
    """
    print("\nDobot Color Sorter — Model Training")
    print(f"  Dataset path : {os.path.abspath(dataset_path)}")
    print(f"  KNN output   : {os.path.abspath(knn_output)}")
    print(f"  SVM output   : {os.path.abspath(svm_output)}\n")

    # Step 1: Load & extract features
    print("Extracting features from augmented dataset...")
    X, y = _load_dataset(dataset_path)

    if X.shape[0] == 0:
        raise RuntimeError(
            "No training samples found. Ensure dataset/augmented/{color}/ "
            "directories are populated before running train_models()."
        )

    print(f"\nTotal samples loaded: {X.shape[0]}  |  Feature dims: {X.shape[1]}")

    # Step 2: Train/Test split for metric reporting
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"Train: {len(X_train)} samples  |  Test: {len(X_test)} samples\n")

    # Step 3: Train KNN (k=3, Euclidean distance)
    print("Training KNN (k=3, Euclidean)...")
    knn = KNeighborsClassifier(n_neighbors=3, metric='euclidean')
    knn.fit(X_train, y_train)
    knn_preds = knn.predict(X_test)
    knn_acc   = accuracy_score(y_test, knn_preds)
    print(f"KNN Test Accuracy: {knn_acc * 100:.1f}%")
    print(classification_report(y_test, knn_preds, target_names=config.CLASSES))

    # Step 4: Train SVM (RBF, C=10, probability=True)
    print("Training SVM (RBF kernel, C=10)...")
    svm = SVC(kernel='rbf', C=10.0, gamma='scale', probability=True)
    svm.fit(X_train, y_train)
    svm_preds = svm.predict(X_test)
    svm_acc   = accuracy_score(y_test, svm_preds)
    print(f"SVM Test Accuracy: {svm_acc * 100:.1f}%")
    print(classification_report(y_test, svm_preds, target_names=config.CLASSES))

    # Step 5: Persist models to disk
    os.makedirs(os.path.dirname(knn_output) or '.', exist_ok=True)
    joblib.dump(knn, knn_output)
    joblib.dump(svm, svm_output)

    print(f"Models saved:")
    print(f"  KNN -> {os.path.abspath(knn_output)}")
    print(f"  SVM -> {os.path.abspath(svm_output)}")
    print("\nTraining complete.\n")


# ---------------------------------------------------------------------------
# CLI entry point: python classifier.py --train
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Dobot Classifier — train or test")
    parser.add_argument('--train', action='store_true',
                        help='Run offline training against dataset/augmented/')
    parser.add_argument('--dataset', default='.',
                        help='Root directory containing dataset/ (default: .)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s')

    if args.train:
        train_models(dataset_path=args.dataset)
    else:
        parser.print_help()
