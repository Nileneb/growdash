import os
import time
import glob
import threading
from typing import Optional, List, Tuple

import serial


class ArduinoManager:
    """Handles serial communication with an Arduino device."""
    
    def __init__(self, port: Optional[str] = None, baud: int = 9600):
        """
        Initialize the Arduino communication manager.
        
        Args:
            port: Serial port to connect to. If None, will auto-detect
            baud: Baud rate for serial communication
        """
        self.port = port
        self.baud = baud
        self.ser: Optional[serial.Serial] = None
        self.lock = threading.Lock()
        self.log_lines: List[str] = []
        self.seq = 0
        self._stop = threading.Event()
        self.t_reader: Optional[threading.Thread] = None
        self._open()

    @staticmethod
    def candidates() -> List[str]:
        """Find potential serial ports the Arduino might be connected to."""
        return sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))

    def _open(self):
        """Open the serial connection to the Arduino."""
        last = None
        ports = [self.port] if self.port else self.candidates()
        for p in ports:
            if not p:
                continue
            try:
                s = serial.Serial(p, self.baud, timeout=0.1)
                time.sleep(0.2)  # Give the connection time to establish
                self.ser = s
                self.port = p
                self._start_reader()
                return
            except Exception as e:
                last = e
        raise RuntimeError(f"Serial open failed. Tried {ports}. Last: {last}")

    def _start_reader(self):
        """Start the background thread that reads data from the Arduino."""
        if self.t_reader and self.t_reader.is_alive():
            return
        self._stop.clear()
        self.t_reader = threading.Thread(target=self._reader_loop, daemon=True)
        self.t_reader.start()

    def _reader_loop(self):
        """Background thread that continuously reads data from the Arduino."""
        while not self._stop.is_set():
            try:
                if not self.ser or not self.ser.is_open:
                    time.sleep(0.2)
                    continue
                b = self.ser.readline()
                if b:
                    line = b.decode("utf-8", errors="ignore").rstrip()
                    self.log_lines.append(line)
                    if len(self.log_lines) > 3000:
                        self.log_lines = self.log_lines[-2000:]
                    self.seq += 1
                else:
                    time.sleep(0.02)
            except Exception:
                time.sleep(0.2)

    def write(self, cmd: str):
        """
        Send a command to the Arduino.
        
        Args:
            cmd: Command string to send
        """
        with self.lock:
            if not self.ser or not self.ser.is_open:
                self._open()
            self.ser.write((cmd.strip() + "\n").encode("utf-8"))
            self.ser.flush()

    def get_since(self, since_seq: int) -> Tuple[List[str], int]:
        """
        Get log lines since a specific sequence number.
        
        Args:
            since_seq: Sequence number to get logs since
            
        Returns:
            Tuple of (log_lines, current_sequence)
        """
        cur = self.seq
        if cur == since_seq or not self.log_lines:
            return [], cur
        
        # Wichtige Änderung: Nur neue Log-Zeilen zurückgeben (seit since_seq)
        if since_seq == 0:
            # Beim ersten Aufruf alle Zeilen zurückgeben
            new_lines = self.log_lines[:]
        else:
            # Die Differenz zwischen den Sequenzen bestimmt, wie viele neue Zeilen es gibt
            diff = cur - since_seq
            # Aber nicht mehr zurückgeben, als wir haben
            diff = min(diff, len(self.log_lines))
            if diff > 0:
                new_lines = self.log_lines[-diff:]
            else:
                new_lines = []
                
        return new_lines, cur
    
    def close(self):
        """Close the connection to the Arduino."""
        self._stop.set()
        if self.t_reader and self.t_reader.is_alive():
            self.t_reader.join(1.0)  # Wait for thread to end with timeout
        if self.ser and self.ser.is_open:
            self.ser.close()
