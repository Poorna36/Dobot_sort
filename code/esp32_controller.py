# esp32_controller.py
# Dobot Color Sorter — ESP32 Serial Communication Wrapper
#
# Handles:
#   - Opening the serial port and waiting for ESP32 boot (2 s)
#   - Reading newline-terminated IR event strings from ESP32
#   - Sending servo command strings to ESP32
#
# Serial Protocol (115200 baud, 8N1):
#   ESP32 → Laptop : "IR1\n", "IR2\n", "IR3\n"
#   Laptop → ESP32 : "1L\n", "1R\n", "2L\n", "2R\n"
#                  (Servo 1 at IR2: L=left push, R=right push)
#                  (Servo 2 at IR3: L=left push, R=right push)

import serial
import time
import logging

import config

logger = logging.getLogger(__name__)

# Build servo command from config angles at import time.
# Protocol: "S{servo_number}:{angle}\n"
# e.g. "S1:0\n" means Servo 1 rotate to 0 degrees.
# The ESP32 firmware parses this and drives the corresponding servo.
_COLOR_TO_CMD = {
    'green':  f"S1:{config.SERVO1_GREEN_ANGLE}\n",   # Servo 1 push to green bin
    'blue':   f"S1:{config.SERVO1_BLUE_ANGLE}\n",    # Servo 1 push to blue bin
    'yellow': f"S2:{config.SERVO2_YELLOW_ANGLE}\n",  # Servo 2 push to yellow bin
    'red':    f"S2:{config.SERVO2_RED_ANGLE}\n",      # Servo 2 push to red bin
}

# Neutral reset commands — sent after push to return paddle to pass-through
_NEUTRAL_CMD = {
    1: f"S1:{config.SERVO1_NEUTRAL_ANGLE}\n",
    2: f"S2:{config.SERVO2_NEUTRAL_ANGLE}\n",
}


class ESP32Controller:
    """
    Thin wrapper around pyserial.Serial for the ESP32 bridge.

    After opening, a mandatory 2-second delay is observed to allow the
    ESP32 to complete its reset/boot cycle (triggered automatically by
    DTR assertion on most CP210x USB-serial chips). Commands sent before
    boot completes are silently dropped by the ESP32.
    """

    def __init__(self):
        try:
            self.serial = serial.Serial(
                port     = config.ESP32_PORT,
                baudrate = config.ESP32_BAUD,
                timeout  = 1.0,   # 1-second readline timeout — non-blocking feel
            )
        except serial.SerialException as e:
            raise ConnectionError(
                f"Cannot open ESP32 on {config.ESP32_PORT}. "
                "Check Device Manager for correct COM port."
            ) from e

        logger.info("ESP32Controller: port %s opened at %d baud.",
                    config.ESP32_PORT, config.ESP32_BAUD)

        # Wait for ESP32 boot — do NOT skip this
        logger.info("ESP32Controller: waiting 2 s for ESP32 boot...")
        time.sleep(2.0)
        self.serial.reset_input_buffer()   # Discard boot banner / garbage bytes
        logger.info("ESP32Controller: ready.")

    def read_line(self):
        """
        Non-blocking read of one newline-terminated line from the serial buffer.

        Returns
        -------
        str or None
            Decoded and stripped string (e.g. 'IR1'), or None if nothing available.
        """
        if self.serial.in_waiting > 0:
            try:
                raw  = self.serial.readline()
                line = raw.decode('utf-8', errors='replace').strip()
                if line:
                    logger.debug("ESP32 → Laptop: '%s'", line)
                return line if line else None
            except serial.SerialException as e:
                logger.error("ESP32Controller: read error — %s", e)
                return None
        return None

    def send_servo_command(self, color):
        """
        Transmit a servo angle command for the given color label.
        Angles are read from config.py — that is the single place to adjust them.

        Parameters
        ----------
        color : str
            One of 'green', 'blue', 'yellow', 'red'.
            'unknown' is silently ignored (cube just passes through).
        """
        cmd = _COLOR_TO_CMD.get(color.lower())
        if cmd is None:
            logger.warning("ESP32Controller: no servo command for color '%s'.", color)
            return

        try:
            self.serial.write(cmd.encode('utf-8'))
            self.serial.flush()
            logger.info("Laptop -> ESP32: '%s'  (color: %s)", cmd.strip(), color)
        except serial.SerialException as e:
            logger.error("ESP32Controller: write error - %s", e)

    def send_servo_neutral(self, color):
        """
        Transmit a neutral reset command for the servo associated with the given color.

        Parameters
        ----------
        color : str
            One of 'green', 'blue', 'yellow', 'red'.
        """
        servo_num = 1 if color.lower() in ('green', 'blue') else 2
        cmd = _NEUTRAL_CMD.get(servo_num)
        if cmd is None:
            logger.warning("ESP32Controller: no neutral command for servo %s.", servo_num)
            return

        try:
            self.serial.write(cmd.encode('utf-8'))
            self.serial.flush()
            logger.info("Laptop -> ESP32: '%s'  (neutral for: %s)", cmd.strip(), color)
        except serial.SerialException as e:
            logger.error("ESP32Controller: write error - %s", e)

    def close(self):
        """Close the serial port. Call during system shutdown."""
        if self.serial.is_open:
            self.serial.close()
            logger.info("ESP32Controller: serial port closed.")
