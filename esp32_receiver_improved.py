#!/usr/bin/env python3
"""
Improved ESP32 Stethoscope Audio Receiver
- Handles framed packets with CRC16 error detection
- Saves raw audio for playback/analysis
- Real-time BPM display and spectral analysis
"""

import socket
import struct
import threading
import numpy as np
from datetime import datetime
import json

# Configuration
LISTEN_PORT = 8765
SAMPLE_RATE = 16000
CHUNK_SIZE = 64

# Packet structure
PACKET_HEADER = 0xAA55


def crc16_ccitt(data):
    """Compute CRC16 CCITT checksum"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def parse_packet(data):
    """
    Parse incoming packet:
    [0xAA55 header (2)] [length (2)] [payload (N)] [CRC16 (2)]
    Returns: (samples_array, is_valid) or (None, False) on error
    """
    if len(data) < 8:
        return None, False

    # Extract header
    header = struct.unpack('>H', data[0:2])[0]
    if header != PACKET_HEADER:
        return None, False

    # Extract length
    length = struct.unpack('>H', data[2:4])[0]
    if len(data) < 4 + length + 2:
        return None, False

    # Extract payload and CRC
    payload = data[4:4 + length]
    received_crc = struct.unpack('>H', data[4 + length:4 + length + 2])[0]

    # Verify CRC
    computed_crc = crc16_ccitt(payload)
    if computed_crc != received_crc:
        print(f"  ⚠️  CRC mismatch: {computed_crc:04X} != {received_crc:04X}")
        return None, False

    # Convert bytes to int16 samples
    samples = np.frombuffer(payload, dtype=np.int16)
    return samples, True


class AudioReceiver:
    def __init__(self):
        self.running = False
        self.socket = None
        self.audio_buffer = []
        self.packet_count = 0
        self.error_count = 0
        self.start_time = None
        self.last_save_time = 0

    def start_server(self):
        """Start listening for audio packets"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("0.0.0.0", LISTEN_PORT))
        self.socket.listen(1)
        print(f"🎧 Listening on port {LISTEN_PORT}...")

        while self.running or True:
            try:
                client, addr = self.socket.accept()
                print(f"✅ ESP32 connected: {addr}")
                self.handle_client(client)
            except KeyboardInterrupt:
                print("\n🛑 Shutting down...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

    def handle_client(self, client):
        """Handle incoming audio stream from ESP32"""
        self.running = True
        self.packet_count = 0
        self.error_count = 0
        self.audio_buffer = []
        self.start_time = datetime.now()
        self.last_save_time = 0

        buffer = bytearray()

        print("📡 Streaming started...")

        try:
            while self.running:
                # Receive data
                try:
                    chunk = client.recv(4096)
                    if not chunk:
                        print("Connection closed by ESP32")
                        break
                except socket.timeout:
                    continue

                buffer.extend(chunk)

                # Try to parse complete packets
                while len(buffer) >= 8:
                    samples, is_valid = parse_packet(buffer)

                    if samples is not None:
                        # Valid packet found
                        self.packet_count += 1
                        self.audio_buffer.extend(samples.astype(np.float32) / 32768.0)

                        # Remove parsed packet from buffer
                        # Find next header for safer parsing
                        found = False
                        for i in range(2, len(buffer)):
                            if (buffer[i - 1] == 0xAA and buffer[i] == 0x55):
                                buffer = buffer[i - 1:]
                                found = True
                                break
                        if not found:
                            buffer.clear()

                        # Auto-save every 30 seconds or ~10K samples
                        if (
                            len(self.audio_buffer) > 160000
                            or datetime.now().timestamp() - self.last_save_time > 30
                        ):
                            self.save_audio()
                            self.last_save_time = datetime.now().timestamp()

                        # Status report
                        if self.packet_count % 160 == 0:  # ~1 second @ 160 packets/sec
                            self.print_status()

                    else:
                        # No valid packet, skip first byte and try again
                        if len(buffer) > 1:
                            buffer = buffer[1:]
                            self.error_count += 1
                        else:
                            break

        except Exception as e:
            print(f"❌ Error handling client: {e}")
        finally:
            client.close()
            self.running = False
            if self.audio_buffer:
                self.save_audio()
            print("📳 Stream ended")

    def save_audio(self):
        """Save buffered audio to WAV file"""
        if not self.audio_buffer:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"stethoscope_{timestamp}.wav"

        try:
            import scipy.io.wavfile as wavfile

            audio_array = np.array(self.audio_buffer, dtype=np.float32)
            # Normalize to avoid clipping
            max_val = np.max(np.abs(audio_array))
            if max_val > 1.0:
                audio_array = audio_array / max_val

            # Convert to int16
            audio_int16 = (audio_array * 32767).astype(np.int16)

            wavfile.write(filename, SAMPLE_RATE, audio_int16)
            duration = len(audio_int16) / SAMPLE_RATE
            print(
                f"💾 Saved {filename} ({len(audio_int16):,} samples, {duration:.1f}s)"
            )
            self.audio_buffer = []

        except ImportError:
            # Fallback: save as raw binary
            filename_raw = filename.replace(".wav", ".raw")
            with open(filename_raw, "wb") as f:
                audio_array = np.array(self.audio_buffer, dtype=np.float32)
                audio_int16 = (audio_array * 32767).astype(np.int16)
                f.write(audio_int16.tobytes())
            print(f"💾 Saved {filename_raw} (raw int16, {len(self.audio_buffer):,} samples)")
            self.audio_buffer = []

    def print_status(self):
        """Print streaming status"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        total_samples = len(self.audio_buffer)

        if total_samples > SAMPLE_RATE:
            # Basic BPM from envelope if available
            audio_arr = np.array(self.audio_buffer[-SAMPLE_RATE :])
            envelope = np.abs(audio_arr)
            envelope_smooth = np.convolve(
                envelope, np.ones(160) / 160, mode="same"
            )
            peaks = np.where(
                (envelope_smooth[1:-1] > np.median(envelope_smooth))
                & (envelope[1:-1] > envelope_smooth[1:-1] * 0.8)
            )[0]
            bpm_str = f"(~{len(peaks)} peaks/sec)" if len(peaks) > 0 else ""
        else:
            bpm_str = ""

        print(
            f"📊 Pkts: {self.packet_count:5d} | Err: {self.error_count:3d} | "
            f"Samples: {total_samples:7d} | Time: {elapsed:.1f}s {bpm_str}"
        )


if __name__ == "__main__":
    print("=" * 60)
    print("   ESP32 Stethoscope Audio Receiver (Improved)")
    print("   Heartbeat Audio Capture & Analysis")
    print("=" * 60)
    print()

    receiver = AudioReceiver()
    try:
        receiver.start_server()
    except KeyboardInterrupt:
        print("\n✋ Stopped by user")
