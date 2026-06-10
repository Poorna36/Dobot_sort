# Electrical Architecture & Pipeline
## Dobot Color Sorting System

---

## Overview

All computation happens on the laptop. ESP32 acts purely as a signal bridge between laptop (Python serial) and physical hardware (IR sensors + servo motors). Dobot is controlled directly from laptop via its own USB connection and Python SDK.

---

## Devices Connected to Laptop

| Device | Connection | Protocol | Purpose |
|---|---|---|---|
| ESP32 | USB (micro USB cable) | Serial 115200 baud | IR signals in, servo commands out |
| Dobot Magician | USB (Dobot cable) | pydobot SDK | Belt control + arm control |
| Logitech C270 | USB | OpenCV VideoCapture | Image capture |

All three connect simultaneously to laptop on separate USB ports (use USB hub if needed).

---

## Power Architecture

### ESP32
```
Source  → Laptop USB (5V via micro USB cable)
Powers  → ESP32 itself + all 3 IR sensors
```

### IR Sensors (FC-51 x3)
```
Source  → ESP32 3.3V pin
Current → ~20mA each × 3 = 60mA total
ESP32 3.3V pin limit → 200mA — well within range
No external power needed
```

### Servo Motors (SG90 x2)
```
Source  → 6V battery (4× AA = 6V)
Current → ~150-200mA each moving, ~10mA idle
Worst case (both fire together) → 400mA peak
Realistic (1 fires at a time) → 200mA
4×AA capacity → 2000-3000mA — sufficient
```

### Dobot Magician
```
Source  → its own dedicated power adapter (included with Dobot)
Laptop USB → data only, not power
```

---

## Breadboard Wiring

Breadboard serves as power distribution hub and common ground point.

### Power Rail (+)
```
+ rail connections:
├── 6V Battery RED wire
├── SG90 Servo 1 RED wire (at IR2)
└── SG90 Servo 2 RED wire (at IR3)
```

### Ground Rail (-)
```
- rail connections:
├── 6V Battery BLACK wire
├── ESP32 GND pin
├── SG90 Servo 1 BROWN wire
└── SG90 Servo 2 BROWN wire
```

All grounds unified — ESP32 logic ground and servo power ground are common. This ensures servo signal wires from ESP32 have a shared voltage reference with servo power. Without common ground, servos receive garbage signals.

---

## ESP32 Pin Assignments

| ESP32 Pin | Connected To | Direction | Purpose |
|---|---|---|---|
| 3.3V | IR1 VCC, IR2 VCC, IR3 VCC | OUT | Power IR sensors |
| GND | Breadboard - rail | OUT | Common ground |
| GPIO 34 | IR Sensor 1 OUT | IN | Cube at camera zone |
| GPIO 35 | IR Sensor 2 OUT | IN | Cube at servo 1 zone (IR2) |
| GPIO 32 | IR Sensor 3 OUT | IN | Cube at servo 2 zone (IR3) |
| GPIO 25 | Servo 1 signal | OUT | PWM to Servo 1 (at IR2) |
| GPIO 26 | Servo 2 signal | OUT | PWM to Servo 2 (at IR3) |
| USB | Laptop | BOTH | Serial 115200 baud + power |

Note: GPIO 34, 35, 32 are input-only pins on ESP32 — perfect for IR sensors.

---

## IR Sensor Wiring (FC-51)

Each FC-51 has 3 pins: VCC, GND, OUT

```
FC-51 Sensor 1 (Camera Zone)
├── VCC → ESP32 3.3V pin
├── GND → ESP32 GND (via breadboard - rail)
└── OUT → ESP32 GPIO 34

FC-51 Sensor 2 (Green/Blue Zone)
├── VCC → ESP32 3.3V pin
├── GND → ESP32 GND (via breadboard - rail)
└── OUT → ESP32 GPIO 35

FC-51 Sensor 3 (Yellow/Red Zone)
├── VCC → ESP32 3.3V pin
├── GND → ESP32 GND (via breadboard - rail)
└── OUT → ESP32 GPIO 32
```

FC-51 OUT behavior:
```
No object detected → OUT = HIGH (3.3V)
Object detected    → OUT = LOW  (0V)
```

Detection range adjustable via onboard potentiometer. Set to ~3-5cm for reliable cube detection without false triggers.

---

## Servo Wiring (SG90)

Each SG90 has 3 wires: Brown (GND), Red (VCC), Orange (Signal)

```
Servo 1 — at IR2 zone (pushes left for green, right for blue)
├── RED    → Breadboard + rail (6V battery)
├── BROWN  → Breadboard - rail (common GND)
└── ORANGE → ESP32 GPIO 25 (PWM signal)

Servo 2 — at IR3 zone (pushes left for yellow, right for red)
├── RED    → Breadboard + rail
├── BROWN  → Breadboard - rail
└── ORANGE → ESP32 GPIO 26
```

---

## Servo Positions (PWM Angles)

| State | Angle | Description |
|---|---|---|
| Neutral / Retracted | 90° | Parallel to belt, cube passes freely |
| Push Left | 0° | Extends left, pushes cube into left bin |
| Push Right | 180° | Extends right, pushes cube into right bin |

**Important:** Actual angles must be calibrated after hardware testing.
Update these values in config.py:
- SERVO_NEUTRAL_ANGLE
- SERVO_PUSH_LEFT_ANGLE
- SERVO_PUSH_RIGHT_ANGLE

Push sequence (controlled by Python timing):
```
Conveyor stops (1.5s) → Servo moves to push angle → Wait for alignment (4.5s) → Servo returns to neutral → Conveyor starts
```

---

## Physical Belt Layout

```
BELT (top view, left to right = direction of travel)

[CUBE START]
      ↓
[CENTERING GUIDE — 3D printed funnel]
      ↓
[IR SENSOR 1 + 📷 WEBCAM above]
      ↓  ~20cm travel
[IR SENSOR 2]
[SERVO 1]   ← single servo, can push left or right
      ↓  ~20cm travel
[IR SENSOR 3]
[SERVO 2]   ← single servo, can push left or right
      ↓
[UNKNOWN / END]
```

Distances (measure and adjust physically):
- IR1 to IR2: ~20cm
- IR2 to IR3: ~20cm
- Camera centered above IR1 position

---

## Signal Flow Diagram

```
PHYSICAL WORLD          ESP32              LAPTOP (Python)

Cube breaks IR1  →  GPIO34 goes LOW  →  Serial "IR1\n"  →  Capture frame
                                                         →  Classify color
                                                         →  Push to queue

Cube breaks IR2  →  GPIO35 goes LOW  →  Serial "IR2\n"  →  Peek queue front
                                                         →  G or B?
                                     ←  Serial "SG\n"   ←  Yes → send servo cmd
ESP32 GPIO25 PWM →  Servo G fires

Cube breaks IR3  →  GPIO32 goes LOW  →  Serial "IR3\n"  →  Peek queue front
                                                         →  Y or R?
                                     ←  Serial "SY\n"   ←  Yes → send servo cmd
ESP32 GPIO27 PWM →  Servo Y fires
                                                         →  Unknown?
                                                         →  Dobot stops belt
                                                         →  Arm removes cube
```

---

## Serial Communication Protocol

Baud rate: 115200

### ESP32 → Laptop (IR events)
| Message | Meaning |
|---|---|
| `IR1\n` | Cube detected at camera zone |
| `IR2\n` | Cube detected at servo pair 1 zone |
| `IR3\n` | Cube detected at servo pair 2 zone |

### Laptop → ESP32 (Servo commands)
| Message | Meaning |
|---|---|
| `1L\n` | Servo 1 push left (GPIO25, for green) |
| `1R\n` | Servo 1 push right (GPIO25, for blue) |
| `2L\n` | Servo 2 push left (GPIO26, for yellow) |
| `2R\n` | Servo 2 push right (GPIO26, for red) |

All messages are newline terminated. ESP32 reads until `\n`.

---

## Components List (Electrical)

| Component | Spec | Qty |
|---|---|---|
| ESP32 DevKit | 3.3V logic, WiFi (unused), USB serial | 1 |
| SG90 Servo | 5V signal compatible at 3.3V, 1.8kg/cm torque | 2 |
| FC-51 IR Sensor | 3.3V-5V, adjustable range, digital OUT | 3 |
| 6V Battery Pack | 4× AA = 6V, ~2500mAh | 1 |
| AA Batteries | 1.5V each | 4 |
| Breadboard | 830 point or mini | 1 |
| Jumper Wires M-M | 20cm | 20 |
| Jumper Wires M-F | 20cm | 15 |
| Insulation Tape | — | 1 roll |

---

## Important Notes

1. **Common ground is mandatory.** If ESP32 GND and battery GND are not connected, servo signal pins have no reference and servos behave erratically.
2. **Do not power servos from ESP32.** ESP32 cannot supply 400mA peak. Always use battery for servo power.
3. **ESP32 3.3V logic is sufficient for SG90 signal.** SG90 servo signal threshold is ~1.5V. ESP32's 3.3V signal triggers it reliably. No level shifter needed.
4. **FC-51 sensitivity must be calibrated.** Use the onboard potentiometer to set detection range to ~3-5cm. Too sensitive = false triggers. Too insensitive = misses cubes.
5. **Dobot has its own power supply.** Never power Dobot from laptop USB or battery. Use its included adapter.
6. **Servo angles must be calibrated after hardware setup.** The placeholder values in config.py (90°, 0°, 180°) must be updated based on actual servo mounting position and paddle geometry.
