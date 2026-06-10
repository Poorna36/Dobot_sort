# camera.py
# Dobot Color Sorter — Webcam Frame Capture Wrapper
#
# Provides a thin abstraction around cv2.VideoCapture so that
# main.py does not interact directly with OpenCV camera objects.
# Single-frame capture only — camera is NOT streamed continuously.

import cv2
import logging

import config

logger = logging.getLogger(__name__)


class CameraWrapper:
    """
    Opens the webcam on initialization and exposes a single get_frame() method.

    The camera remains open for the lifetime of the process so each capture
    call is instant (no open/close overhead per frame).
    """

    def __init__(self):
        self.cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if not self.cap.isOpened():
            raise IOError(
                f"Cannot open webcam at index {config.CAMERA_INDEX}. "
                "Check that the Logitech C270 is plugged in."
            )
        # Prefer 640×480 native resolution of the C270
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        logger.info("CameraWrapper: webcam opened (index %d).", config.CAMERA_INDEX)

    def get_frame(self):
        """
        Grab and decode a single frame from the webcam buffer.

        Returns
        -------
        frame : np.ndarray or None
            BGR image of shape (480, 640, 3), or None on read failure.
        """
        ret, frame = self.cap.read()
        if not ret or frame is None:
            logger.error("CameraWrapper: failed to read frame.")
            return None
        return frame

    def release(self):
        """Release the camera resource. Call on shutdown."""
        self.cap.release()
        logger.info("CameraWrapper: webcam released.")
