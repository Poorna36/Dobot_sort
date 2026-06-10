# ESP32 Firmware Documentation
## Signal Bridge — IR Input & Servo Output

---

## Role

ESP32 is a dumb signal bridge. It has no decision-making logic.

```
IR Sensors → ESP32 → Serial → Laptop    (events)
Laptop → Serial → ESP32 → Servos        (commands)
```

All decisions (which servo to fire, when to stop belt) are made on the laptop. ESP32 just reports sensor events and executes servo commands.

---

## Firmware Platform

**Recommended:** Arduino framework via Arduino IDE or PlatformIO
**Language:** C++ (Arduino)
**Board:** ESP32 DevKit V1

---

## Pin Map

| Pin | Mode | Connected To |
|---|---|---|
| GPIO 34 | INPUT | IR Sensor 1 OUT (camera zone) |
| GPIO 35 | INPUT | IR Sensor 2 OUT (Servo 1 zone) |
| GPIO 32 | INPUT | IR Sensor 3 OUT (Servo 2 zone) |
| GPIO 25 | OUTPUT | Servo 1 (at IR2) |
| GPIO 26 | OUTPUT | Servo 2 (at IR3) |
| 3.3V | POWER OUT | IR Sensor 1,2,3 VCC |
| GND | COMMON GND | Breadboard - rail |
| USB | SERIAL | Laptop (115200 baud) |

GPIO 34, 35, 32 are input-only pins — ideal for sensors, no accidental output.

---

## Complete ESP32 Firmware

```cpp
#include <ESP32Servo.h>

// IR sensor digital input pins (FC-51 active low)
#define IR1_PIN 34   // Camera zone (IR1)
#define IR2_PIN 35   // Servo 1 zone (IR2)
#define IR3_PIN 32   // Servo 2 zone (IR3)

// Servo PWM signal output pins
#define SERVO_1_PIN 25  // Servo 1 at IR2
#define SERVO_2_PIN 26  // Servo 2 at IR3

// Default neutral angle on startup (paddle parallel to belt)
#define DEFAULT_NEUTRAL 90

// Software Debounce duration in milliseconds
#define DEBOUNCE_MS 300

Servo servo1;
Servo servo2;

unsigned long lastIR1 = 0;
unsigned long lastIR2 = 0;
unsigned long lastIR3 = 0;

void setup() {
  Serial.begin(115200);

  // Configure IR sensor pins as inputs
  pinMode(IR1_PIN, INPUT);
  pinMode(IR2_PIN, INPUT);
  pinMode(IR3_PIN, INPUT);

  // Attach servo signals to PWM pins
  servo1.attach(SERVO_1_PIN);
  servo2.attach(SERVO_2_PIN);

  // Set all servo arms to default neutral position
  servo1.write(DEFAULT_NEUTRAL);
  servo2.write(DEFAULT_NEUTRAL);

  delay(500);
  Serial.println("ESP32 READY");
}

void loop() {
  unsigned long now = millis();

  // Evaluate Sensor 1 (Camera Zone)
  if (digitalRead(IR1_PIN) == LOW && (now - lastIR1 > DEBOUNCE_MS)) {
    lastIR1 = now;
    Serial.println("IR1");
  }

  // Evaluate Sensor 2 (Green/Blue Zone)
  if (digitalRead(IR2_PIN) == LOW && (now - lastIR2 > DEBOUNCE_MS)) {
    lastIR2 = now;
    Serial.println("IR2");
  }

  // Evaluate Sensor 3 (Yellow/Red Zone)
  if (digitalRead(IR3_PIN) == LOW && (now - lastIR3 > DEBOUNCE_MS)) {
    lastIR3 = now;
    Serial.println("IR3");
  }

  // Read incoming serial commands from laptop
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim(); // Strip carriage returns on Windows

    // Dynamic Protocol Format: "S<servo_number>:<angle>"
    // e.g. "S1:0" (Servo 1 to 0 deg), "S2:180" (Servo 2 to 180 deg)
    if (cmd.startsWith("S") && cmd.indexOf(':') != -1) {
      int colonIdx = cmd.indexOf(':');
      char servoChar = cmd.charAt(1); // '1' or '2'
      int angle = cmd.substring(colonIdx + 1).toInt();

      if (servoChar == '1') {
        servo1.write(angle);
      } else if (servoChar == '2') {
        servo2.write(angle);
      }
    }
  }
}
```

---

## Key Implementation Notes

### Debouncing
FC-51 IR sensors can bounce (trigger multiple times for one cube pass). DEBOUNCE_MS = 300ms ensures each cube only sends one IR event. If cubes are placed closer than 300ms apart at belt speed, reduce this value.

### Blocking pushServo()
pushServo() uses delay() — it blocks the loop for 400ms during servo push. During this time, IR events can be missed. This is acceptable because:
- Python controls timing (conveyor stops before servo fires)
- Only one servo fires at a time
- Belt is stopped during servo operation, so no cubes arrive during push
- PUSH_HOLD_MS is legacy; actual timing controlled by Python (config.py)

### Serial.readStringUntil('\n')
Reads full command string until newline. Handles any command length. trim() removes carriage return on Windows systems.

### ESP32Servo Library
Standard Arduino Servo library conflicts with ESP32 PWM. Use ESP32Servo library instead. Install via Arduino IDE Library Manager: search "ESP32Servo".

---

## Arduino IDE Setup

```
1. Install Arduino IDE
2. Add ESP32 board:
   File → Preferences → Additional Board Manager URLs:
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
3. Tools → Board Manager → search "esp32" → install
4. Tools → Board → ESP32 Dev Module
5. Install ESP32Servo library (Library Manager)
6. Select correct COM port
7. Upload firmware
```

---

## Firmware Upload Note

After uploading firmware, ESP32 resets. Python script must wait 2 seconds before sending any serial commands. This is handled in integration code (time.sleep(2) after serial.Serial() opens).

---

## Testing Firmware Without Full System

```
1. Open Arduino Serial Monitor at 115200 baud
2. Block IR1 sensor with hand → should see "IR1" printed
3. Block IR2 sensor → should see "IR2"
4. Block IR3 sensor → should see "IR3"
5. Type "1L" in Serial Monitor → Servo 1 should push left and retract
6. Type "1R" → Servo 1 should push right and retract
7. Type "2L" → Servo 2 should push left and retract
8. Type "2R" → Servo 2 should push right and retract
```

All 2 servos and all 3 IR sensors can be verified in under 5 minutes without running Python.
