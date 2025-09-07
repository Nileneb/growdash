import os
import time
import threading
import subprocess
import numpy as np
from typing import Optional, Tuple

import cv2

# Versuche PyAudio zu importieren, falls nicht vorhanden, deaktiviere Audio
try:
    import pyaudio
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("PyAudio nicht installiert - Audio-Funktionalität ist deaktiviert")


class Camera:
    """Manages camera operations for capturing images, video and audio."""
    
    def __init__(self, width: int = 800, height: int = 450, fps: int = 8,
                 audio_enabled: bool = True, audio_rate: int = 44100):
        """
        Initialize the camera manager.
        
        Args:
            width: Capture width in pixels
            height: Capture height in pixels
            fps: Frames per second
            audio_enabled: Whether to capture audio
            audio_rate: Audio sample rate
        """
        self.width = int(os.getenv("CAM_WIDTH", width))
        self.height = int(os.getenv("CAM_HEIGHT", height))
        self.fps = int(os.getenv("CAM_FPS", fps))
        self.dev = self._find_device(os.getenv("CAM_DEVICE"))
        
        # Video capture
        self.cap = None
        self.latest = None
        self._lock = threading.Lock()
        self._id = 0
        self._stop = False
        self._thr = threading.Thread(target=self._loop, daemon=True)
        
        # Audio capture
        self.audio_enabled = audio_enabled and AUDIO_AVAILABLE
        self.audio_rate = int(os.getenv("AUDIO_RATE", audio_rate))
        self.audio_chunk = 1024  # Chunk size for audio capture
        self.audio_channels = 1  # Mono
        self.audio = None
        self.audio_stream = None
        self.latest_audio = None
        self.audio_lock = threading.Lock()
        self._audio_id = 0
        self._audio_thr = None
        
        # Format für PyAudio nur setzen, wenn verfügbar
        if AUDIO_AVAILABLE:
            self.audio_format = pyaudio.paInt16
        
        # Start the video capture thread
        self._thr.start()
        
        # Start audio capture if enabled
        if self.audio_enabled:
            self._init_audio()

    @staticmethod
    def _find_device(explicit: Optional[str] = None) -> Optional[str]:
        """
        Find a suitable video device.
        
        Args:
            explicit: Explicitly specified device path
            
        Returns:
            Device path or None if not found
        """
        # Check explicit device if provided
        if explicit and os.path.exists(explicit):
            return explicit
            
        # Otherwise check common video devices
        for d in ("/dev/video0", "/dev/video1", "/dev/video2", "/dev/video3"):
            if os.path.exists(d):
                return d
                
        return None
        
    def _find_audio_device(self) -> Optional[int]:
        """
        Find a suitable audio device.
        
        Returns:
            Audio device index or None if not found
        """
        if not self.audio_enabled:
            return None
            
        try:
            p = pyaudio.PyAudio()
            # Versuche, das Standardeingabegerät zu ermitteln
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get('maxInputChannels') > 0:  # Gerät hat ein Mikrofon
                    p.terminate()
                    return i
            p.terminate()
        except Exception as e:
            print(f"Fehler bei der Audiogerätesuche: {e}")
        
        return None
        
    def _init_audio(self):
        """Initialize audio capture."""
        if not AUDIO_AVAILABLE:
            print("PyAudio ist nicht installiert. Audio-Aufnahme deaktiviert.")
            self.audio_enabled = False
            return
            
        try:
            self.audio = pyaudio.PyAudio()
            device_index = self._find_audio_device()
            
            if device_index is not None:
                self.audio_stream = self.audio.open(
                    format=self.audio_format,
                    channels=self.audio_channels,
                    rate=self.audio_rate,
                    input=True,
                    frames_per_buffer=self.audio_chunk,
                    input_device_index=device_index,
                    stream_callback=self._audio_callback
                )
                self.audio_stream.start_stream()
                print(f"Audio-Aufnahme gestartet: {self.audio_rate}Hz, Gerät {device_index}")
            else:
                print("Kein Audiogerät gefunden.")
                self.audio_enabled = False
        except Exception as e:
            print(f"Fehler bei der Audio-Initialisierung: {e}")
            self.audio_enabled = False
            
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback function for audio capture."""
        with self.audio_lock:
            self.latest_audio = in_data
            self._audio_id += 1
        return (None, pyaudio.paContinue)

    def _open(self) -> bool:
        """
        Open the camera device.
        
        Returns:
            True if opened successfully, False otherwise
        """
        dev = self._find_device(os.getenv("CAM_DEVICE"))
        if not dev:
            return False
            
        if self.cap:
            self.cap.release()
            
        self.dev = dev
        self.cap = cv2.VideoCapture(self.dev, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        return self.cap.isOpened()

    def _loop(self):
        """Background thread that continuously captures frames."""
        backoff = 0.5
        while not self._stop:
            if not self.cap or not self.cap.isOpened():
                if self._open():
                    backoff = 0.5
                else:
                    time.sleep(min(backoff, 5))
                    backoff = min(backoff * 1.5, 5)
                    continue
                    
            ok, frame = self.cap.read()
            if not ok:
                # Connection lost - try to reconnect
                self.cap.release()
                time.sleep(0.2)
                continue
                
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with self._lock:
                    self.latest = buf.tobytes()
                    self._id += 1
                    
            time.sleep(1.0 / max(self.fps, 1))

    def wait_new(self, last_id: int, timeout: float = 2.0) -> Tuple[Optional[bytes], int]:
        """
        Wait for a new frame to be captured.
        
        Args:
            last_id: ID of the last frame received
            timeout: Maximum time to wait in seconds
            
        Returns:
            Tuple of (frame_bytes, frame_id) or (None, last_id) if timed out
        """
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self._lock:
                if self._id != last_id and self.latest is not None:
                    return self.latest, self._id
            time.sleep(0.02)
            
        return None, last_id
    
    def get_latest(self) -> Tuple[Optional[bytes], int]:
        """
        Get the latest frame immediately without waiting.
        
        Returns:
            Tuple of (frame_bytes, frame_id) or (None, 0) if no frame available
        """
        with self._lock:
            if self.latest is not None:
                return self.latest, self._id
        return None, 0
        
    def get_latest_audio(self) -> Tuple[Optional[bytes], int]:
        """
        Get the latest audio chunk immediately without waiting.
        
        Returns:
            Tuple of (audio_bytes, audio_id) or (None, 0) if no audio available
        """
        if not self.audio_enabled:
            return None, 0
            
        with self.audio_lock:
            if self.latest_audio is not None:
                return self.latest_audio, self._audio_id
        return None, 0
        
    def wait_new_audio(self, last_id: int, timeout: float = 0.5) -> Tuple[Optional[bytes], int]:
        """
        Wait for a new audio chunk to be captured.
        
        Args:
            last_id: ID of the last audio chunk received
            timeout: Maximum time to wait in seconds
            
        Returns:
            Tuple of (audio_bytes, audio_id) or (None, last_id) if timed out
        """
        if not self.audio_enabled:
            return None, last_id
            
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self.audio_lock:
                if self._audio_id != last_id and self.latest_audio is not None:
                    return self.latest_audio, self._audio_id
            time.sleep(0.01)
            
        return None, last_id
    
    def close(self):
        """Close the camera and release resources."""
        self._stop = True
        if self._thr.is_alive():
            self._thr.join(1.0)  # Wait for thread to end with timeout
        if self.cap:
            self.cap.release()
            
        # Clean up audio resources
        if self.audio_enabled and self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception:
                pass
                
        if self.audio:
            try:
                self.audio.terminate()
            except Exception:
                pass
