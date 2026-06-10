# main.py
# Dobot Color Sorter — System Orchestrator & Entry Point
#
# Threading model:
#   Main Thread        : initialization → belt start → idle loop (Ctrl+C exits)
#   Serial Listener    : daemon thread, loops reading ESP32 serial indefinitely
#   Capture Workers    : spawned by threading.Timer per IR1 event (one per cube)
#
# FIFO Queue:
#   color_queue (deque) — enqueued after classification (IR1), dequeued at IR2/IR3.
#   Thread-safe for single append (right) and single popleft operations.

import threading
import time
import logging
from collections import deque

import config
from classifier import detect_cube, extract_features, TwoStageClassifier
from camera import CameraWrapper
from esp32_controller import ESP32Controller
from dobot_controller import DobotController

# ---------------------------------------------------------------------------
# Logging setup — INFO level with timestamps
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d [%(levelname)-8s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Orchestrator
# ---------------------------------------------------------------------------

class SystemOrchestrator:

    def __init__(self):
        self.color_queue = deque()   # FIFO queue: strings like 'green', 'unknown'
        self.running     = False

        # -- Load ML models --------------------------------------------------
        logger.info("Loading ML models...")
        self.model = TwoStageClassifier(
            knn_path='models/knn_model.pkl',
            svm_path='models/svm_model.pkl'
        )

        # -- Connect hardware ------------------------------------------------
        logger.info("Connecting webcam...")
        self.camera = CameraWrapper()

        logger.info("Connecting ESP32...")
        self.esp32 = ESP32Controller()

        logger.info("Connecting Dobot...")
        self.dobot = DobotController()

        logger.info("All hardware connected.\n")

    # -----------------------------------------------------------------------
    # Startup & Shutdown
    # -----------------------------------------------------------------------

    def start(self):
        self.running = True

        # Daemon thread reads serial port continuously
        self._serial_thread = threading.Thread(
            target=self._serial_loop, daemon=True, name="SerialListener"
        )
        self._serial_thread.start()

        # Start conveyor belt
        self.dobot.start_belt()
        logger.info("=== Color Sorting System ACTIVE — place cubes on belt. ===\n")

    def stop(self):
        self.running = False
        logger.info("Shutting down...")
        self.dobot.shutdown()
        self.camera.release()
        self.esp32.close()
        logger.info("Shutdown complete.")

    # -----------------------------------------------------------------------
    # Serial Listener — runs in background daemon thread
    # -----------------------------------------------------------------------

    def _serial_loop(self):
        """
        Continuously reads the ESP32 serial port and dispatches handlers.
        Runs forever until self.running is False.
        """
        while self.running:
            line = self.esp32.read_line()
            if line == 'IR1':
                self._handle_ir1()
            elif line == 'IR2':
                self._handle_ir2()
            elif line == 'IR3':
                self._handle_ir3()
            time.sleep(0.005)   # 5 ms yield — keeps CPU free, latency negligible

    # -----------------------------------------------------------------------
    # IR1 Handler — Camera Zone
    # -----------------------------------------------------------------------

    def _handle_ir1(self):
        """
        Cube has entered the camera scan zone.
        Spawns a timer thread so the conveyor can center the cube under the
        lens before capture. The serial listener thread is NOT blocked.
        """
        logger.info("IR1 triggered — scheduling capture in %.2f s.", config.CAPTURE_DELAY)
        threading.Timer(config.CAPTURE_DELAY, self._capture_and_classify).start()

    def _capture_and_classify(self):
        """
        Worker: capture one frame, detect cube, extract features, run classifier,
        then append the result to the FIFO queue.
        Runs in its own short-lived thread (spawned by Timer).
        """
        frame = self.camera.get_frame()
        if frame is None:
            logger.error("Frame capture failed — enqueueing 'unknown' to preserve queue alignment.")
            self.color_queue.append('unknown')
            return

        cropped, bbox = detect_cube(frame)
        if cropped is None:
            logger.warning("No cube detected in frame — enqueueing 'unknown'.")
            self.color_queue.append('unknown')
            return

        feat                     = extract_features(cropped)
        label, confidence, model = self.model.classify(feat)

        logger.info(
            "Classified: %-8s | conf: %5.1f%% | model: %s | queue depth: %d",
            label.upper(), confidence * 100, model, len(self.color_queue) + 1
        )
        self.color_queue.append(label)

    # -----------------------------------------------------------------------
    # IR2 Handler — Green / Blue Servo Zone
    # -----------------------------------------------------------------------

    def _handle_ir2(self):
        """
        Cube has reached the Servo 1 zone (near IR2).
        Stop conveyor, allow servo to align, then push cube left or right.
        Green → push left, Blue → push right.
        Yellow, Red, and Unknown cubes pass through after conveyor restart.
        """
        if not self.color_queue:
            logger.warning("IR2 triggered but queue is empty — ignoring.")
            return

        color = self.color_queue[0]   # peek

        if color in ('green', 'blue'):
            # Stop conveyor
            self.dobot.stop_belt()
            logger.info("IR2: conveyor stopped. Sending servo push command...")
            
            # Send servo command
            self.color_queue.popleft()
            self.esp32.send_servo_command(color)
            logger.info("IR2: sorted %s — servo command sent.", color.upper())
            
            # Wait for servo to reach position and stay there
            total_hold = config.SERVO_MOVE_TIME + config.SERVO_HOLD_TIME
            logger.info("IR2: waiting %.1fs (move + hold) at push position.", total_hold)
            time.sleep(total_hold)
            
            # Return servo to neutral
            logger.info("IR2: resetting servo to neutral.")
            self.esp32.send_servo_neutral(color)
            
            # Wait for servo to return to neutral
            logger.info("IR2: waiting %.1fs for servo to return to neutral.", config.SERVO_RETURN_TIME)
            time.sleep(config.SERVO_RETURN_TIME)
            
            # Restart conveyor
            self.dobot.start_belt()
            logger.info("IR2: conveyor restarted.")
        else:
            logger.info("IR2: front=%s — passing through to IR3.", color.upper())

    # -----------------------------------------------------------------------
    # IR3 Handler — Yellow / Red Servo Zone & Reject
    # -----------------------------------------------------------------------

    def _handle_ir3(self):
        """
        Cube has reached the Servo 2 zone (near IR3).
        Stop conveyor, allow servo to align, then push cube left or right.
        Yellow -> push left, Red -> push right.
        Unknown cubes -> just pass through (no arm reject).
        """
        if not self.color_queue:
            logger.warning("IR3 triggered but queue is empty — ignoring.")
            return

        color = self.color_queue[0]   # peek

        if color in ('yellow', 'red'):
            # Stop conveyor
            self.dobot.stop_belt()
            logger.info("IR3: conveyor stopped. Sending servo push command...")
            
            # Send servo command
            self.color_queue.popleft()
            self.esp32.send_servo_command(color)
            logger.info("IR3: sorted %s — servo command sent.", color.upper())
            
            # Wait for servo to reach position and stay there
            total_hold = config.SERVO_MOVE_TIME + config.SERVO_HOLD_TIME
            logger.info("IR3: waiting %.1fs (move + hold) at push position.", total_hold)
            time.sleep(total_hold)
            
            # Return servo to neutral
            logger.info("IR3: resetting servo to neutral.")
            self.esp32.send_servo_neutral(color)
            
            # Wait for servo to return to neutral
            logger.info("IR3: waiting %.1fs for servo to return to neutral.", config.SERVO_RETURN_TIME)
            time.sleep(config.SERVO_RETURN_TIME)
            
            # Restart conveyor
            self.dobot.start_belt()
            logger.info("IR3: conveyor restarted.")

        elif color == 'unknown':
            # Unknown cubes simply pass through — no arm, no reject
            self.color_queue.popleft()
            logger.warning("IR3: UNKNOWN cube passed through unsorted — no action taken.")

        else:
            # Edge case: cube reached end of belt without being sorted
            logger.error(
                "IR3: color '%s' reached end of belt unsorted! "
                "Check belt timing and IR sensor calibration.", color
            )
            self.color_queue.popleft()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    orchestrator = SystemOrchestrator()
    orchestrator.start()

    try:
        logger.info("Press Ctrl+C to stop the system.\n")
        while True:
            time.sleep(1.0)

    except KeyboardInterrupt:
        logger.info("\nCtrl+C received — stopping system.")
    finally:
        orchestrator.stop()


if __name__ == '__main__':
    main()
