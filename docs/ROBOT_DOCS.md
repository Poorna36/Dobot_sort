# Robot Documentation
## Dobot Magician — Belt & Arm Configuration

---

## Hardware Overview

**Device:** Dobot Magician
**Connection:** USB to laptop
**SDK:** pydobot (Python)
**Control:** Laptop Python script via pydobot API
**Components used:** Conveyor belt + robotic arm with vacuum gripper

---

## Conveyor Belt

### Physical Specs
| Property | Value |
|---|---|
| Belt type | Dobot Magician conveyor belt accessory |
| Belt width | ~50mm (measure physically and confirm) |
| Usable belt length | ~400-500mm |
| Drive | DC motor, software speed controlled |
| Direction | Bidirectional (we use forward only) |

### Speed Configuration
```python
# Belt speed is fixed in software — never varies during operation
# This eliminates all belt-speed-dependent timing issues

BELT_SPEED = 0.5        # range: 0.0 to 1.0
BELT_DIRECTION = 1      # 1 = forward, -1 = reverse

# Start belt
device.conveyor_belt(BELT_SPEED, BELT_DIRECTION)

# Stop belt
device.conveyor_belt(0, BELT_DIRECTION)
```

**Important:** Belt speed is set ONCE at startup and never changed during normal operation. Fixed speed makes all timing calculations (IR trigger to servo zone travel time) deterministic.

### Belt Speed Calibration (do once before demo)
```
1. Set belt speed in config.py
2. Place a cube at IR1 position
3. Time how long it takes to reach IR2 position
4. Measure IR1-to-IR2 distance physically
5. Confirm: distance / time = expected speed
6. Adjust BELT_SPEED in config.py if needed
7. Lock speed — do not change after calibration
```

### Belt Control API
```python
from pydobot import Dobot

device = Dobot(port='COM4', verbose=False)

# Start moving forward
device.conveyor_belt(0.5, 1)

# Stop
device.conveyor_belt(0, 1)

# The belt stops immediately — no coast/deceleration
# Safe to call from any thread
```

---

## Robotic Arm

### Physical Configuration
| Property | Value |
|---|---|
| End effector | Vacuum suction cup (white rubber) |
| Reach | ~320mm |
| Degrees of freedom | 4 (J1, J2, J3, J4) |
| Coordinate system | Cartesian (X, Y, Z, R) |

### Vacuum Gripper
```python
# Vacuum ON — picks up object
device.suck(True)

# Vacuum OFF — releases object
device.suck(False)

# Wait ~0.8s after vacuum ON before moving
# Suction needs time to create seal on foam cube
```

### Arm Positions — Calibrate Physically

These coordinates MUST be calibrated physically before first run. Use Dobot Studio's jog mode to position arm and read coordinates.

```python
# Positions to calibrate (fill in after physical calibration)
# Format: (X mm, Y mm, Z mm, R degrees)

ARM_HOME = (200, 0, 50, 0)          # safe resting position — fill in
ARM_PICKUP = (x, y, z, 0)          # directly above cube on belt — fill in
ARM_PICKUP_Z_DOWN = z_value         # Z height where suction touches cube top
ARM_PICKUP_Z_UP = z_value + 40      # lifted height (40mm above pickup)
ARM_REJECT_BOX = (x, y, z, 0)      # above reject box — fill in
```

### Calibration Procedure
```
1. Open Dobot Studio on laptop
2. Connect Dobot
3. Use jog controls (or teach mode) to move arm manually
4. Position 1: Move arm to HOME position (safe, out of belt way)
   → Read X, Y, Z, R from Dobot Studio → save as ARM_HOME
5. Position 2: Move arm directly above pickup point on belt
   → Lower Z until suction cup just touches cube surface
   → Read X, Y, Z → save as ARM_PICKUP
6. Position 3: Move arm above reject box
   → Read X, Y, Z → save as ARM_REJECT_BOX
7. Enter all values in config.py
8. Test once with a foam cube before demo
```

### Arm Movement API
```python
# Move to position — non-blocking
device.move_to(x, y, z, r, wait=False)

# Move to position — blocking (waits until arm arrives)
device.move_to(x, y, z, r, wait=True)

# Always use wait=True in arm sequence
# to ensure arm fully arrives before next command
```

### Full Reject Sequence (called when unknown color detected)
```python
def arm_remove_sequence(device):
    # 1. Stop belt first
    device.conveyor_belt(0, 1)
    
    # 2. Wait for cube to settle (belt stops instantly)
    time.sleep(0.5)
    
    # 3. Move above pickup point (high Z)
    device.move_to(
        ARM_PICKUP[0], ARM_PICKUP[1], ARM_PICKUP_Z_UP, ARM_PICKUP[3],
        wait=True
    )
    
    # 4. Lower to cube surface
    device.move_to(
        ARM_PICKUP[0], ARM_PICKUP[1], ARM_PICKUP_Z_DOWN, ARM_PICKUP[3],
        wait=True
    )
    
    # 5. Vacuum ON
    device.suck(True)
    time.sleep(0.8)    # suction grip time
    
    # 6. Lift cube (important — lift before lateral movement)
    device.move_to(
        ARM_PICKUP[0], ARM_PICKUP[1], ARM_PICKUP_Z_UP, ARM_PICKUP[3],
        wait=True
    )
    
    # 7. Move to reject box
    device.move_to(
        ARM_REJECT_BOX[0], ARM_REJECT_BOX[1], ARM_REJECT_BOX[2], ARM_REJECT_BOX[3],
        wait=True
    )
    
    # 8. Release
    device.suck(False)
    time.sleep(0.5)
    
    # 9. Return home
    device.move_to(
        ARM_HOME[0], ARM_HOME[1], ARM_HOME[2], ARM_HOME[3],
        wait=True
    )
    
    # 10. Resume belt
    device.conveyor_belt(BELT_SPEED, BELT_DIRECTION)
```

---

## Dobot Connection

```python
from pydobot import Dobot
import serial.tools.list_ports

def find_dobot_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'CP210' in port.description or 'Dobot' in port.description:
            return port.device
    return None

port = find_dobot_port()
device = Dobot(port=port, verbose=False)
```

If auto-detect fails, manually check Device Manager (Windows) or `ls /dev/tty*` (Linux/Mac) after plugging in Dobot.

---

## Dobot Safety Rules

1. **Always lift Z before lateral movement.** Never drag arm sideways at low Z — it will hit the belt or cubes.
2. **Always return to HOME after reject sequence.** Arm must be out of belt path before belt resumes.
3. **Belt must be stopped before arm moves.** Never run arm and belt simultaneously — arm could collide with moving cubes.
4. **Vacuum must be OFF at home position.** Always release suction before returning home.
5. **Test arm sequence 3-4 times before demo** with a real foam cube to confirm positions are accurate.

---

## Physical Setup Notes

- Reject box must be placed within arm reach (~320mm from Dobot base)
- Reject box position must not interfere with belt path
- Arm home position must be above and clear of belt
- Pickup position X,Y must align precisely with where unknown cube stops on belt (at IR3 end, since unknown is detected at IR3)
- Vacuum cup must be clean and undamaged for reliable suction on foam

---

## Dobot Belt + Arm — What Is NOT Used

- Dobot's built-in color sensor (not used — we use webcam + ML)
- Dobot Studio sorting scripts (not used — we use pydobot API directly)
- Gripper end effector (not used — vacuum suction only)
- Dobot's built-in teach-repeat mode (not used — programmatic control only)
