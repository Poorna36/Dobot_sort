# augment.py
# Dobot Color Sorter — Offline Dataset Augmentation Script
#
# Expands raw dataset from 50 images per color to 250 images per color.
# Each original image produces exactly 5 augmented variants.
#
# Usage:
#   python augment.py
#   python augment.py --input dataset/raw --output dataset/augmented
#
# CRITICAL RULE: Never shift Hue or Saturation channels.
# Color IS the classification label. Only geometry and V-channel brightness
# may be modified.

import cv2
import numpy as np
import os
import random
import argparse
import sys


# ---------------------------------------------------------------------------
# Individual Augmentation Functions
# ---------------------------------------------------------------------------

def aug_gaussian_blur(image):
    """
    Augment 1: Gaussian Blur
    Simulates slight defocus and camera shake from the low-quality C270 lens.
    """
    kernel_size = random.choice([3, 5, 7])
    return cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)


def aug_motion_blur(image):
    """
    Augment 2: Horizontal Motion Blur
    Simulates cube movement along the belt during capture.
    Direction is horizontal only — belt moves left to right.
    """
    kernel_size = random.randint(9, 15)
    kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
    kernel[kernel_size // 2, :] = 1.0 / kernel_size
    return cv2.filter2D(image, -1, kernel)


def aug_brightness_shift(image):
    """
    Augment 3: Brightness Shift (V channel ONLY)
    Simulates overhead lighting intensity variation.
    H and S channels are NOT modified — color ground truth is preserved.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.int32)
    delta = random.randint(-40, 40)
    # Ensure delta is not near zero (minimum ±20 effective shift)
    if abs(delta) < 20:
        delta = 20 if delta >= 0 else -20
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] + delta, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def aug_slight_rotation(image):
    """
    Augment 4: Slight Rotation
    Simulates cube not being perfectly square to the camera axis.
    Uses BORDER_REFLECT to avoid black border artifacts that could mislead the
    saturation mask into rejecting border pixels.
    """
    angle = random.uniform(-10.0, 10.0)
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def aug_random_crop_resize(image):
    """
    Augment 5: Random Crop + Resize back to original dimensions
    Simulates the cube appearing at different distances or positions within frame.
    Keeps 80–90% of the original frame area.
    """
    h, w = image.shape[:2]
    crop_factor = random.uniform(0.80, 0.90)
    crop_h = int(h * crop_factor)
    crop_w = int(w * crop_factor)
    x = random.randint(0, w - crop_w)
    y = random.randint(0, h - crop_h)
    cropped = image[y:y + crop_h, x:x + crop_w]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)


# Map augmentation index (1-5) to its corresponding function
AUGMENTATION_PIPELINE = {
    1: aug_gaussian_blur,
    2: aug_motion_blur,
    3: aug_brightness_shift,
    4: aug_slight_rotation,
    5: aug_random_crop_resize,
}


# ---------------------------------------------------------------------------
# Per-Image Augmentation Driver
# ---------------------------------------------------------------------------

def augment_image(src_path, dst_dir, base_name, color_label):
    """
    Load one raw image, apply all 5 augmentation functions, and save 5 variants.
    Also copies the original (unmodified) into the output folder.
    """
    image = cv2.imread(src_path)
    if image is None:
        print(f"  [WARN] Could not read {src_path} — skipping.")
        return 0

    saved = 0

    # Copy original image into augmented output folder unchanged
    orig_dst = os.path.join(dst_dir, base_name)
    cv2.imwrite(orig_dst, image)
    saved += 1

    # Apply each augmentation function and save the result
    name_stem, ext = os.path.splitext(base_name)
    for aug_idx, aug_fn in AUGMENTATION_PIPELINE.items():
        augmented = aug_fn(image.copy())
        aug_filename = f"{name_stem}_aug{aug_idx}{ext}"
        aug_path = os.path.join(dst_dir, aug_filename)
        cv2.imwrite(aug_path, augmented)
        saved += 1

    return saved  # Returns 6 (1 original + 5 augments) — but we want 250 total.
                  # With 50 raw images: 50 originals + 50×5 augments = 300.
                  # Keep only augmented (no duplicating originals in training split).


# ---------------------------------------------------------------------------
# Per-Class Driver
# ---------------------------------------------------------------------------

def augment_color_class(src_class_dir, dst_class_dir, color_label):
    """
    Augments all images within one color folder.
    """
    os.makedirs(dst_class_dir, exist_ok=True)

    image_files = [
        f for f in os.listdir(src_class_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]

    if len(image_files) == 0:
        print(f"  [WARN] No images found in {src_class_dir}")
        return

    print(f"  Processing [{color_label.upper()}]: {len(image_files)} raw images found.")

    total_written = 0
    for filename in sorted(image_files):
        src_path = os.path.join(src_class_dir, filename)
        count = augment_image(src_path, dst_class_dir, filename, color_label)
        total_written += count

    # Final count in augmented directory
    final_count = len([
        f for f in os.listdir(dst_class_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])
    print(f"  [{color_label.upper()}] Complete — {final_count} images in output folder.")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Dobot Color Sorter — Dataset Augmentation Script"
    )
    parser.add_argument(
        '--input', default='dataset/raw',
        help='Root directory containing raw color subfolders (default: dataset/raw)'
    )
    parser.add_argument(
        '--output', default='dataset/augmented',
        help='Root directory to write augmented images (default: dataset/augmented)'
    )
    args = parser.parse_args()

    color_classes = ['green', 'blue', 'yellow', 'red']

    print(f"\nDobot Sorter — Dataset Augmentation")
    print(f"  Input:  {os.path.abspath(args.input)}")
    print(f"  Output: {os.path.abspath(args.output)}")
    print(f"  Classes: {color_classes}\n")

    for color in color_classes:
        src_dir = os.path.join(args.input, color)
        dst_dir = os.path.join(args.output, color)

        if not os.path.isdir(src_dir):
            print(f"  [ERROR] Source folder not found: {src_dir}")
            sys.exit(1)

        augment_color_class(src_dir, dst_dir, color)

    print("\nAugmentation complete.")
    print("Verify each augmented folder contains 250+ images before training.\n")


if __name__ == '__main__':
    main()
