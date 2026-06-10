# test_mock.py
# Dobot Color Sorter — Phase 2.2 Mock Test (No Hardware Required)
#
# Patches out: ESP32 serial, Dobot arm+belt, webcam.
# Replaces them with stubs that simulate IR events and return real
# augmented images from disk so the ML pipeline is exercised end-to-end.
#
# Usage:
#   python test_mock.py
#
# Expected outcome:
#   - 8 cubes (2 per color) are injected via simulated IR1 events.
#   - Classification runs against real augmented images.
#   - IR2/IR3 dequeue and "sort" each cube.
#   - Queue must be empty at the end — proves FIFO sync is correct.

import threading
import time
import logging
import os
import random
import cv2
from collections import deque
from unittest.mock import MagicMock, patch

import config
from classifier import detect_cube, extract_features, TwoStageClassifier

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d [%(levelname)-8s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('MOCK_TEST')


# ---------------------------------------------------------------------------
# Mock Hardware Classes
# ---------------------------------------------------------------------------

class MockCameraWrapper:
    """Returns a random augmented image of the requested color from disk."""

    def __init__(self):
        self._dataset_root = r'D:\data set\dataset\augmented'
        self._current_color = None
        logger.info("[MockCamera] initialized — serving images from %s", self._dataset_root)

    def set_next_color(self, color):
        """Pre-stage the color for the next get_frame() call."""
        self._current_color = color

    def get_frame(self):
        if self._current_color is None:
            return None
        color_dir = os.path.join(self._dataset_root, self._current_color)
        if not os.path.isdir(color_dir):
            logger.error("[MockCamera] folder missing: %s", color_dir)
            return None
        files = [f for f in os.listdir(color_dir) if f.lower().endswith(('.jpg', '.png'))]
        if not files:
            return None
        chosen = random.choice(files)
        img = cv2.imread(os.path.join(color_dir, chosen))
        logger.info("[MockCamera] serving %s/%s", self._current_color, chosen)
        return img

    def release(self):
        logger.info("[MockCamera] released.")


class MockESP32Controller:
    """Stores sent servo commands for verification. read_line() returns from a queue."""

    def __init__(self):
        self._event_queue = deque()
        self.servo_log = []       # records (color, cmd) tuples
        logger.info("[MockESP32] initialized — no serial port opened.")

    def inject_event(self, event_str):
        """Push a simulated IR event that read_line() will return."""
        self._event_queue.append(event_str)

    def read_line(self):
        if self._event_queue:
            return self._event_queue.popleft()
        return None

    def send_servo_command(self, color):
        logger.info("[MockESP32] SERVO CMD -> color=%s", color)
        self.servo_log.append(color)

    def send_servo_neutral(self, color):
        logger.info("[MockESP32] SERVO NEUTRAL -> color=%s", color)
        self.servo_log.append(f"{color}_neutral")

    def close(self):
        logger.info("[MockESP32] closed.")


class MockDobotController:
    """Logs belt start/stop and arm movements — no real hardware."""

    def __init__(self):
        self.belt_running = False
        logger.info("[MockDobot] initialized — no Dobot connected.")

    def start_belt(self):
        self.belt_running = True
        logger.info("[MockDobot] belt STARTED.")

    def stop_belt(self):
        self.belt_running = False
        logger.info("[MockDobot] belt STOPPED.")

    def shutdown(self):
        self.stop_belt()
        logger.info("[MockDobot] shutdown complete.")


# ---------------------------------------------------------------------------
# Patched SystemOrchestrator (inline — avoids import-time hardware init)
# ---------------------------------------------------------------------------

class MockOrchestrator:
    """
    Mirrors the real SystemOrchestrator but uses mock hardware.
    Timing is compressed (no real CAPTURE_DELAY / CONVEYOR_STOP_DURATION waits).
    """

    def __init__(self):
        self.color_queue = deque()
        self.running = False

        logger.info("Loading ML models...")
        self.model = TwoStageClassifier(
            knn_path='models/knn_model.pkl',
            svm_path='models/svm_model.pkl'
        )

        self.camera = MockCameraWrapper()
        self.esp32  = MockESP32Controller()
        self.dobot  = MockDobotController()
        logger.info("Mock hardware ready.\n")

    def _handle_ir1(self, true_color):
        """Simulate IR1: capture a frame of the given color and classify it."""
        logger.info("IR1 triggered — capturing %s cube.", true_color)
        self.camera.set_next_color(true_color)
        frame = self.camera.get_frame()
        if frame is None:
            logger.error("Frame capture failed -> enqueueing 'unknown'.")
            self.color_queue.append('unknown')
            return

        cropped, bbox = detect_cube(frame)
        if cropped is None:
            logger.warning("No cube detected -> enqueueing 'unknown'.")
            self.color_queue.append('unknown')
            return

        feat = extract_features(cropped)
        label, confidence, model_used = self.model.classify(feat)

        match = "OK" if label == true_color else "MISMATCH"
        logger.info(
            "Classified: %-8s | conf: %5.1f%% | model: %s | expected: %s [%s] | queue depth: %d",
            label.upper(), confidence * 100, model_used,
            true_color.upper(), match, len(self.color_queue) + 1
        )
        self.color_queue.append(label)

    def _handle_ir2(self):
        """Simulate IR2: dequeue green/blue, pass others."""
        if not self.color_queue:
            logger.warning("IR2 triggered but queue is empty.")
            return

        color = self.color_queue[0]
        if color in ('green', 'blue'):
            self.dobot.stop_belt()
            self.color_queue.popleft()
            self.esp32.send_servo_command(color)
            logger.info("IR2: sorted %s via Servo 1.", color.upper())
            self.esp32.send_servo_neutral(color)
            self.dobot.start_belt()
        else:
            logger.info("IR2: %s passes through to IR3.", color.upper())

    def _handle_ir3(self):
        """Simulate IR3: dequeue yellow/red/unknown."""
        if not self.color_queue:
            logger.warning("IR3 triggered but queue is empty.")
            return

        color = self.color_queue[0]
        if color in ('yellow', 'red'):
            self.dobot.stop_belt()
            self.color_queue.popleft()
            self.esp32.send_servo_command(color)
            logger.info("IR3: sorted %s via Servo 2.", color.upper())
            self.esp32.send_servo_neutral(color)
            self.dobot.start_belt()
        elif color == 'unknown':
            # Unknown cubes just pass through — no arm reject
            self.color_queue.popleft()
            logger.warning("IR3: UNKNOWN cube passed through unsorted.")
        else:
            logger.error("IR3: unexpected color '%s' at end of belt!", color)
            self.color_queue.popleft()


# ---------------------------------------------------------------------------
# Test Scenario
# ---------------------------------------------------------------------------

def run_mock_test():
    print("=" * 70)
    print("  PHASE 2.2 — Mock Stand-Alone Test (No Hardware)")
    print("  Simulates 8 cubes through the full pipeline.")
    print("=" * 70 + "\n")

    orch = MockOrchestrator()

    # Test cubes: 2 of each color, shuffled
    test_cubes = ['green', 'blue', 'yellow', 'red'] * 2
    random.shuffle(test_cubes)
    logger.info("Test sequence: %s\n", [c.upper() for c in test_cubes])

    results = {'correct': 0, 'total': 0, 'mismatches': []}

    for i, true_color in enumerate(test_cubes):
        logger.info("--- Cube %d / %d ---", i + 1, len(test_cubes))

        # Step 1: IR1 — camera zone
        orch._handle_ir1(true_color)

        # Check classification
        if orch.color_queue:
            classified_as = orch.color_queue[-1]
            results['total'] += 1
            if classified_as == true_color:
                results['correct'] += 1
            else:
                results['mismatches'].append((true_color, classified_as))

        # Step 2: IR2 — servo zone 1
        orch._handle_ir2()

        # Step 3: IR3 — servo zone 2 (only if cube passed through IR2)
        if orch.color_queue:
            orch._handle_ir3()

        print()   # visual separator

    # ---------------------------------------------------------------------------
    # Final Report
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)

    # Queue sync check
    queue_ok = len(orch.color_queue) == 0
    print(f"\n  FIFO Queue at end     : {list(orch.color_queue)}")
    print(f"  Queue empty (sync OK) : {'PASS' if queue_ok else 'FAIL'}")

    # Classification accuracy
    acc = results['correct'] / results['total'] * 100 if results['total'] > 0 else 0
    print(f"\n  Classification        : {results['correct']}/{results['total']} correct ({acc:.0f}%)")
    if results['mismatches']:
        print(f"  Mismatches            : {results['mismatches']}")

    # Servo log
    print(f"\n  Servo commands sent   : {orch.esp32.servo_log}")

    # Overall verdict
    all_pass = queue_ok and results['correct'] == results['total']
    print(f"\n  {'='*40}")
    print(f"  OVERALL: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
    print(f"  {'='*40}\n")

    return 0 if all_pass else 1


if __name__ == '__main__':
    exit(run_mock_test())
