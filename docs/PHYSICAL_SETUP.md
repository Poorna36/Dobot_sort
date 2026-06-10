# Physical Setup & Assembly Guide
## Dobot Color Sorting System

---

## Overview

This document covers physical placement, mounting, and assembly of all components on and around the Dobot Magician conveyor belt. No permanent modifications to the Dobot equipment — everything is removable.

---

## Belt Layout — Top View

```
BELT DIRECTION OF TRAVEL →

 ┌────────────────────────────────────────────────────────┐
 │                                                        │
 │  [CENTERING   [IR1]    [IR2]         [IR3]             │
 │   GUIDE]       📷      S1⬛         S2⬛               │
 │                                                        │
 └────────────────────────────────────────────────────────┘
       ↓           ↓        ↓            ↓
    funnel     camera   Servo 1      Servo 2
    aligns     zone    (pushes       (pushes
    cubes              left/right)   left/right)
```

### Distances (measure and mark with tape before demo)

```
Start of belt → Centering guide:     ~5cm
Centering guide → IR1/Camera zone:   ~10cm
IR1 → IR2:                           ~15-20cm
IR2 → IR3:                           ~15-20cm
IR3 → belt end:                      ~10cm
```

Mark positions on belt frame with masking tape labels before demo day.

---

## Component Placement

### Centering Guide
- 3D printed funnel shape
- Placed at start of belt
- Narrows belt path to center-align cubes
- Rests on belt frame edges — no glue needed
- Ensures cube is consistently centered under camera ROI

### Webcam (Logitech C270)
- Mounted directly above IR1 position
- Height: ~20-30cm above belt surface
- Angle: straight down (top view) for consistent color capture
- Mount: tape or clamp to a stand/rod above belt
- Must NOT move after ROI calibration — tape it firmly

### LED Light
- Positioned above camera zone
- Diffused overhead lighting preferred (not direct spotlight)
- Eliminates shadows and color shift from ambient light
- USB powered from laptop

### IR Sensor 1 (Camera Zone)
- Positioned at same X location as webcam
- Mounted on side of belt, beam crosses belt width
- Height: ~2-3cm above belt surface (below cube top)
- Cube should reliably break beam as it enters camera zone
- Adjust FC-51 potentiometer until LED indicator shows clean trigger

### IR Sensor 2 (Green/Blue Zone)
- Positioned 15-20cm after IR1
- Same mounting method as IR1
- Must trigger BEFORE cube reaches servo paddles
- Place ~2-3cm before servo paddle position

### IR Sensor 3 (Yellow/Red Zone)
- Positioned 15-20cm after IR2
- Same mounting method
- Place ~2-3cm before second servo pair paddles

### Servo Motor 1 (at IR2 Zone)
```
Single servo positioned near IR2 sensor
Can rotate to push cube LEFT (for green) or RIGHT (for blue)
Mounted on one side of belt, paddle extends across belt width
When fired: paddle rotates to target angle, deflects cube to appropriate side
```

### Servo Motor 2 (at IR3 Zone)
```
Single servo positioned near IR3 sensor
Can rotate to push cube LEFT (for yellow) or RIGHT (for red)
Same arrangement as Servo 1
```

### Servo Mounting
- SG90 servo body sits on belt frame edge
- Servo horn with cardboard/plastic paddle faces inward over belt
- Secure servo body with tape or rubber band to belt frame
- Fully removable — no permanent attachment

### Servo Paddle Construction
```
Materials: thick cardboard or thin plastic sheet
Size: belt width × 4cm height
Attachment: hot glue paddle to servo horn arm
Horn attachment: press onto servo shaft, tighten with included screw
Angle at neutral (90°): paddle parallel to belt sides (cube passes freely)
Angle at push left (0°): paddle sweeps to push cube to left bin
Angle at push right (180°): paddle sweeps to push cube to right bin
Note: Actual angles to be calibrated after hardware testing (see config.py)
```

### Bins / Collection Boxes
```
Left bins  (Green, Yellow): placed to left of belt
Right bins (Blue, Red):     placed to right of belt
Reject box:                 placed within Dobot arm reach
Bin openings should be wide enough to catch deflected foam cubes
Cardboard boxes work fine
```

---

## Breadboard Placement
- Place beside belt, near Arduino/ESP32
- Must be within jumper wire reach of all 4 servo BROWN and RED wires
- Keep away from belt — vibration can loosen jumper wires

---

## Cable Management
- Bundle servo extension cables together with cable ties or tape
- Route cables away from belt surface to avoid cube interference
- ESP32 USB cable must reach laptop without tension
- Dobot USB cable already long enough (comes with Dobot)

---

## Pre-Demo Physical Checklist

### Electrical
- [ ] 6V battery inserted and fresh
- [ ] Battery wires secure in breadboard + rail
- [ ] Both servo RED wires in + rail
- [ ] Both servo BROWN wires in - rail
- [ ] ESP32 GND in - rail
- [ ] Both servo ORANGE wires connected to correct ESP32 GPIO pins
- [ ] All IR sensor VCC → ESP32 3.3V
- [ ] All IR sensor GND → ESP32 GND (via breadboard)
- [ ] All IR sensor OUT → correct ESP32 GPIO input pins
- [ ] ESP32 USB connected to laptop
- [ ] Dobot USB connected to laptop
- [ ] Webcam USB connected to laptop

### Physical
- [ ] Centering guide in place
- [ ] Webcam position fixed and not moving
- [ ] LED light on and illuminating scan zone evenly
- [ ] IR1 sensor aligned — test by passing hand through beam
- [ ] IR2 sensor aligned — test by passing hand through beam
- [ ] IR3 sensor aligned — test by passing hand through beam
- [ ] Both servo paddles at neutral (parallel to belt)
- [ ] Bins positioned correctly on each side
- [ ] Reject box within arm reach
- [ ] No cables crossing belt path

### Software
- [ ] ROI calibrated to camera position (run calibration script once)
- [ ] Arm positions calibrated (ARM_PICKUP, ARM_REJECT_BOX, ARM_HOME)
- [ ] Belt speed set and tested in config.py
- [ ] Servo angles calibrated (SERVO_NEUTRAL_ANGLE, SERVO_PUSH_LEFT_ANGLE, SERVO_PUSH_RIGHT_ANGLE)
- [ ] Conveyor stop duration tested (CONVEYOR_STOP_DURATION)
- [ ] Servo alignment duration tested (SERVO_ALIGN_DURATION)
- [ ] FC-51 sensitivity adjusted (objects trigger cleanly at belt height)
- [ ] ML models trained and saved in models/ folder
- [ ] requirements.txt installed

---

## ROI Calibration (One-Time Setup)

Run this before training and before demo to confirm ROI is correct:

```python
import cv2

cap = cv2.VideoCapture(0)
while True:
    ret, frame = cap.read()
    cv2.rectangle(frame, (ROI_X1, ROI_Y1), (ROI_X2, ROI_Y2), (0,255,0), 2)
    cv2.imshow('ROI Check', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
cap.release()
cv2.destroyAllWindows()
```

Adjust ROI_X1, ROI_Y1, ROI_X2, ROI_Y2 in config.py until the green box perfectly frames the cube when it is centered in the scan zone. Save and do not move the camera after this.

---

## FC-51 Sensitivity Calibration

Each FC-51 has a small blue potentiometer on the board:

```
Turn clockwise   → less sensitive (shorter range)
Turn anticlockwise → more sensitive (longer range)

Target: sensor detects cube at belt height (~3-4cm from sensor)
        but does NOT trigger on belt surface itself

Test: place a foam cube in front of sensor
      indicator LED on FC-51 board should light up
      remove cube — LED should go off
      if LED stays on always → sensitivity too high, turn clockwise
      if LED never turns on  → sensitivity too low, turn anticlockwise
```

Do this for all 3 sensors before first run.
