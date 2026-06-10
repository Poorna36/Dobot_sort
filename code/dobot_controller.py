# dobot_controller.py
# Dobot Color Sorter — Conveyor Belt Controller
#
# Provides:
#   start_belt()  — begin moving belt forward at configured speed
#   stop_belt()   — halt belt immediately
#   shutdown()    — stop belt and close connection
#
# NOTE: This system does NOT use the Dobot robotic arm.
#       Only the conveyor belt is controlled via the Dobot.
#       Sorting is handled entirely by servo paddles on the ESP32.
#       Unknown/unidentified cubes simply pass through to the end.

import logging
from pydobot import Dobot

import config

logger = logging.getLogger(__name__)


class DobotController:
    """
    Thin wrapper around the pydobot SDK for conveyor belt control only.
    No arm movement, no vacuum — just belt start/stop.
    """

    def __init__(self):
        try:
            self.device = Dobot(port=config.DOBOT_PORT, verbose=False)
        except Exception as e:
            raise ConnectionError(
                f"Cannot connect to Dobot on {config.DOBOT_PORT}. "
                "Check Device Manager for the correct COM port and ensure "
                "Dobot is powered on."
            ) from e

        logger.info("DobotController: connected on %s.", config.DOBOT_PORT)

    # -----------------------------------------------------------------------
    # Conveyor Belt
    # -----------------------------------------------------------------------

    def start_belt(self):
        """Start the conveyor belt at the configured speed and direction."""
        self.device.conveyor_belt(config.BELT_SPEED, config.BELT_DIRECTION)
        logger.info("DobotController: belt started (speed=%.1f, dir=%d).",
                    config.BELT_SPEED, config.BELT_DIRECTION)

    def stop_belt(self):
        """Halt the conveyor belt immediately (no deceleration ramp)."""
        self.device.conveyor_belt(0.0, config.BELT_DIRECTION)
        logger.info("DobotController: belt stopped.")

    # -----------------------------------------------------------------------
    # Shutdown
    # -----------------------------------------------------------------------

    def shutdown(self):
        """
        Safe shutdown: stop belt and close the Dobot connection.
        Call this from the main thread on KeyboardInterrupt or exit.
        """
        logger.info("DobotController: shutting down...")
        self.stop_belt()
        self.device.close()
        logger.info("DobotController: Dobot connection closed.")
