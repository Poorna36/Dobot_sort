# Physical Hardware Connection & Wiring Guide
## Dobot Color Sorter — Quick Connection Reference

This document provides a step-by-step wiring guide for connecting the IR sensors, servos, ESP32 microcontroller, and external battery pack.

---

## 1. Grounding Question: Can I ground IR sensors directly to the ESP32?

**Yes, absolutely!** 

Electrically, all **GND** pins on the ESP32 board are connected to the same copper ground plane internally. Grounding an IR sensor directly to a GND pin on the ESP32 is identical to grounding it to the breadboard's negative rail.

### Why do we use the Breadboard Ground Rail then?
* **Pin Limits:** Most ESP32 DevKit boards only have **2 or 3 physical GND pins**.
* **Connection Count:** The system has **5 ground connections** in total (3 IR sensors + 2 servos + 1 battery pack).
* **Convenience:** Running a single jumper wire from one ESP32 GND pin to the breadboard `-` rail turns that entire rail into a shared ground bus, giving you more than enough slots to plug in all ground wires safely.

*If you have a wiring harness, custom PCB, or want to splice wires directly to the ESP32 GND pins, you are free to do so!*

---

## 2. Core Electrical Guidelines (Crucial)

> [!IMPORTANT]
> **Common Ground is Mandatory**
> You must link the ESP32 logic ground and the external servo battery ground together (e.g. by connecting the ESP32 GND to the battery negative `-` wire). Without a common ground reference, control signals from the ESP32 to the servos will be floating/unstable, causing the servos to jitter, twitch, or fail to move.

> [!CAUTION]
> **Do NOT Power Servos from ESP32 Pins**
> Servos draw high spikes of current (up to 400mA each when pushing under load). The ESP32's onboard voltage regulators are not rated to supply this and will burn out or repeatedly brown out (restart). Always power the servos from the **6V Battery Pack**.

> [!TIP]
> **Powering IR Sensors**
> IR sensors (FC-51) draw very little current (~20mA each). It is completely safe to power all three of them in parallel directly from the ESP32's **3.3V** output pin.

---

## 3. Wiring Diagram

### A. Power Distribution Hub (Breadboard Rails)

| Rail | Connected Component Wires | Purpose |
| :--- | :--- | :--- |
| **Negative Rail (`-`)** | 1. ESP32 **GND** pin<br>2. 6V Battery Pack **Black (-) wire**<br>3. Servo 1 **Brown (GND) wire**<br>4. Servo 2 **Brown (GND) wire**<br>5. IR Sensors 1, 2, and 3 **GND pins** | Common Ground Bus |
| **Positive Rail (`+`)** | 1. 6V Battery Pack **Red (+) wire**<br>2. Servo 1 **Red (VCC) wire**<br>3. Servo 2 **Red (VCC) wire** | +6V Servo Power Bus |

---

### B. ESP32 Pin Connections

| ESP32 Pin | Connected Component | Wire Color | Role in System | Python Telemetry Expectation |
| :--- | :--- | :--- | :--- | :--- |
| **3.3V** | **VCC** pins of IR Sensors 1, 2, 3 | Red | Power sensors | System Power |
| **GND** | Breadboard **`-` Rail** (or direct sensor ground) | Black | Common Ground reference | Ground reference |
| **GPIO 34** | **OUT** pin of **IR Sensor 1** (Camera Zone) | Yellow/Green | Detects cube entering scan area | Laptop expects `IR1\n` serial message |
| **GPIO 35** | **OUT** pin of **IR Sensor 2** (Servo 1 Zone) | Yellow/Green | Detects cube entering sorting zone 1 | Laptop expects `IR2\n` serial message |
| **GPIO 32** | **OUT** pin of **IR Sensor 3** (Servo 2 Zone) | Yellow/Green | Detects cube entering sorting zone 2 | Laptop expects `IR3\n` serial message |
| **GPIO 25** | **Signal** pin of **Servo 1** | Orange | Rotates Servo 1 (Green/Blue) | Python sends `S1:{angle}\n` |
| **GPIO 26** | **Signal** pin of **Servo 2** | Orange | Rotates Servo 2 (Yellow/Red) | Python sends `S2:{angle}\n` |

---

## 4. Hardware Component Pinout Reference

```
  FC-51 IR SENSOR              SG90 SERVO MOTOR
   (Front View)                  (Cable Colors)
  ┌───────────┐                  ┌───────────┐
  │  [IR] [IR]│                  │           │
  │           │                  │   SG90    │
  │  V G O    │                  │           │
  └──│─│─│────┘                  └──┬─┬─┬────┘
     │ │ └── OUT (GPIO Pin)         │ │ └── Orange (Signal to GPIO)
     │ └──── GND (Ground Rail)      │ └──── Red (VCC to +6V Battery)
     └────── VCC (3.3V Power)       └────── Brown (GND to Ground Rail)
```

---

## 5. Physical Hardware Calibration Steps

1. **IR Sensor Sensitivity Calibration:**
   * Power the ESP32.
   * Place a sorting cube on the black conveyor belt.
   * Use a small screwdriver to turn the blue potentiometer brass screw on the FC-51 sensor.
   * Adjust it so the onboard indicator LED turns **ON** when the cube is in front of the sensor, but stays **OFF** when looking at the empty conveyor belt.
2. **Servo Arm Mechanical Alignment:**
   * Power on the ESP32 with the servos connected. They will automatically move to the default `90°` neutral position.
   * Physically mount the plastic paddle horns onto the servo gears so that they are **parallel** to the sides of the conveyor belt (creating an open lane for cubes to pass).
   * Tighten the center horn screws.
