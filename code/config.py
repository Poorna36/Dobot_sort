# config.py
# Dobot Color Sorter — System Configuration Constants
# =====================================================================
# THIS IS THE SINGLE SOURCE OF TRUTH for all hardware settings.
# All thresholds, calibration values, servo angles, and port numbers
# live here. Edit this file after physical calibration.
# Do NOT hardcode values in any other file.
# =====================================================================

# ---------------------------------------------------------------------------
# Hardware Communication Ports
# ---------------------------------------------------------------------------
# Windows: 'COMx' — check Device Manager after plugging in each device
# Linux/Mac: '/dev/ttyUSBx' or '/dev/ttyACMx'
ESP32_PORT = 'COM3'         # ESP32 USB-serial port (IR sensors + servos)
ESP32_BAUD = 115200         # Must match Serial.begin() in ESP32 firmware

DOBOT_PORT = 'COM4'         # Dobot Magician (conveyor belt control only)

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAMERA_INDEX  = 0            # 0 = first connected webcam (Logitech C270)
CAPTURE_DELAY = 0.15         # Seconds after IR1 fires before camera grabs frame.
                             # Allows belt to center cube under camera viewport.

# ---------------------------------------------------------------------------
# ML — Cube Detection (HSV Masking + Contour)
# ---------------------------------------------------------------------------
DETECTION_MIN_AREA = 5000    # px² — contours smaller than this are noise
DETECTION_PADDING  = 15      # px — padding around bounding box on all sides

# ---------------------------------------------------------------------------
# ML — Classification Cascade Thresholds
# ---------------------------------------------------------------------------
# KNN: distance ratio test (Lowe's ratio).
#   ratio = d_nearest / d_second_nearest
#   If ratio <  KNN_RATIO_THRESHOLD  → confident → use KNN result.
#   If ratio >= KNN_RATIO_THRESHOLD  → ambiguous → escalate to SVM.
KNN_RATIO_THRESHOLD = 0.7

# SVM: max class probability threshold.
#   If max(predict_proba) >= SVM_PROBA_THRESHOLD → use SVM result.
#   If max(predict_proba) <  SVM_PROBA_THRESHOLD → classify as "unknown".
SVM_PROBA_THRESHOLD = 0.6

# Physical sorting classes. "unknown" is NOT a trained class —
# it is inferred by failing both confidence checks above.
# Unknown cubes simply pass through to the end of the belt unsorted.
CLASSES = ['green', 'blue', 'yellow', 'red']

# ---------------------------------------------------------------------------
# Conveyor Belt (Dobot Magician)
# ---------------------------------------------------------------------------
BELT_SPEED     = 0.5         # 0.0 (stop) to 1.0 (full speed)
BELT_DIRECTION = 1           # 1 = forward along sorting zones

# ---------------------------------------------------------------------------
# Servo System — Physical Layout
# ---------------------------------------------------------------------------
#
#   Camera          Servo 1 (IR2)         Servo 2 (IR3)
#   [  C  ]---IR1---[  S1  ]---IR2---[  S2  ]---IR3--->  end of belt
#                   green|blue        yellow|red
#                   left | right      left  | right
#
# Two servo motors are mounted beside the belt. Each servo has a paddle
# that can push cubes into one of two bins (left or right).
#
# Servo 1 at IR2:  sorts GREEN (push left) and BLUE (push right)
# Servo 2 at IR3:  sorts YELLOW (push left) and RED (push right)
# Unknown cubes:   pass through both zones unsorted (no arm reject).

# ---------------------------------------------------------------------------
# Servo Angles (degrees) — CALIBRATE AFTER PHYSICAL MOUNTING
# ---------------------------------------------------------------------------
# Neutral : paddle parallel to belt — cube passes freely
# Push angles : paddle rotates to deflect cube into the left or right bin
#
# >>> ADJUST THESE VALUES to match your physical servo mounting <<<

# Servo 1 (at IR2 zone — handles GREEN and BLUE)
SERVO1_NEUTRAL_ANGLE = 90   # degrees — paddle parallel, cube passes through
SERVO1_GREEN_ANGLE   = 0    # degrees — push left for GREEN bin
SERVO1_BLUE_ANGLE    = 180  # degrees — push right for BLUE bin

# Servo 2 (at IR3 zone — handles YELLOW and RED)
SERVO2_NEUTRAL_ANGLE = 90   # degrees — paddle parallel, cube passes through
SERVO2_YELLOW_ANGLE  = 0    # degrees — push left for YELLOW bin
SERVO2_RED_ANGLE     = 180  # degrees — push right for RED bin

# ---------------------------------------------------------------------------
# Servo Timing (seconds)
# ---------------------------------------------------------------------------
# Full servo push cycle:
#   1. MOVE to push angle   — as fast as possible (budget ≤ 1.2 s)
#   2. HOLD at push angle   — cube needs time to slide into the bin
#   3. RETURN to neutral    — as fast as possible (budget ≤ 1.2 s)
#
# Belt stays stopped for the entire cycle.

SERVO_MOVE_TIME   = 1.2   # seconds — max time for servo to reach push angle
SERVO_HOLD_TIME   = 4.0   # seconds — how long paddle stays at push position
SERVO_RETURN_TIME = 1.2   # seconds — max time for servo to return to neutral

# Total cycle = MOVE + HOLD + RETURN  (auto-calculated, do not edit)
SERVO_TOTAL_CYCLE = SERVO_MOVE_TIME + SERVO_HOLD_TIME + SERVO_RETURN_TIME  # 6.4 s

