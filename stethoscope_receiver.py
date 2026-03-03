#!/usr/bin/env python3
"""
stethoscope_receiver.py

Connects to the ESP32 stethoscope over TCP, receives raw 16-bit PCM audio,
plays it live through your speakers, and saves it as a .wav file when done.

Usage:
    python stethoscope_receiver.py                          # uses defaults
    python stethoscope_receiver.py --ip 192.168.1.42        # custom IP
    python stethoscope_receiver.py --ip 192.168.1.42 --port 8888 --output recording.wav

Dependencies:
    pip install numpy sounddevice
"""

import socket
import wave
import time
import argparse
import threading
import sys
import os
from datetime import datetime

try:
    import numpy as np
    import sounddevice as sd
    LIVE_PLAYBACK = True
except ImportError:
    LIVE_PLAYBACK = False
    print("Note: Install 'numpy' and 'sounddevice' for live playback.")
    print("      pip install numpy sounddevice")
    print("      Recording will still be saved to WAV.\n")

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
CHUNK_SAMPLES = 256


def create_output_filename(base_name):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(base_name)
    return f"{name}_{timestamp}{ext}"


def receive_and_save(ip, port, output_file, duration=None, live=True):
    output_path = create_output_filename(output_file)
    print(f"Output file: {output_path}")
    print(f"Connecting to {ip}:{port}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    try:
        sock.connect((ip, port))
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"Connection failed: {e}")
        print("Make sure:")
        print("  1. ESP32 is powered on and connected to WiFi")
        print("  2. The IP address matches what the ESP32 printed to Serial")
        print("  3. Your computer is on the same WiFi network")
        return

    sock.settimeout(1)
    print("Connected! Recording... (Ctrl+C to stop)\n")

    wav_file = wave.open(output_path, 'wb')
    wav_file.setnchannels(CHANNELS)
    wav_file.setsampwidth(SAMPLE_WIDTH)
    wav_file.setframerate(SAMPLE_RATE)

    audio_stream = None
    if live and LIVE_PLAYBACK:
        try:
            audio_stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype='int16',
                blocksize=CHUNK_SAMPLES
            )
            audio_stream.start()
            print("Live playback enabled")
        except Exception as e:
            print(f"Could not start live playback: {e}")
            audio_stream = None

    total_bytes = 0
    total_samples = 0
    start_time = time.time()
    running = True

    def print_status():
        nonlocal total_bytes, total_samples
        while running:
            elapsed = time.time() - start_time
            if total_samples > 0:
                mins = int(elapsed) // 60
                secs = int(elapsed) % 60
                kb = total_bytes / 1024
                sys.stdout.write(
                    f"\r  Recording: {mins:02d}:{secs:02d} | "
                    f"{total_samples:,} samples | "
                    f"{kb:.1f} KB received    "
                )
                sys.stdout.flush()
            time.sleep(0.5)

    status_thread = threading.Thread(target=print_status, daemon=True)
    status_thread.start()

    try:
        while True:
            if duration and (time.time() - start_time) >= duration:
                print(f"\nDuration limit ({duration}s) reached.")
                break

            try:
                data = sock.recv(CHUNK_SAMPLES * SAMPLE_WIDTH)
            except socket.timeout:
                continue
            except ConnectionResetError:
                print("\nConnection reset by ESP32.")
                break

            if not data:
                print("\nESP32 disconnected.")
                break

            wav_file.writeframes(data)
            total_bytes += len(data)
            total_samples += len(data) // SAMPLE_WIDTH

            if audio_stream and LIVE_PLAYBACK:
                try:
                    padded = data if len(data) % 2 == 0 else data + b'\x00'
                    samples = np.frombuffer(padded, dtype=np.int16)
                    audio_stream.write(samples)
                except Exception:
                    pass

    except KeyboardInterrupt:
        print("\n\nStopping...")

    finally:
        running = False
        sock.close()
        wav_file.close()
        if audio_stream:
            audio_stream.stop()
            audio_stream.close()

        elapsed = time.time() - start_time
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        file_size = os.path.getsize(output_path)

        print("\n" + "=" * 50)
        print(f"  Recording saved: {output_path}")
        print(f"  Duration:        {mins:02d}:{secs:02d}")
        print(f"  Samples:         {total_samples:,}")
        print(f"  File size:       {file_size / 1024:.1f} KB")
        print(f"  Format:          {SAMPLE_RATE} Hz, 16-bit, mono WAV")
        print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Receive and record audio from ESP32 Stethoscope over WiFi"
    )
    parser.add_argument("--ip", type=str, default="192.168.1.100",
                        help="ESP32 IP address (check Serial Monitor)")
    parser.add_argument("--port", type=int, default=8888,
                        help="TCP port (default: 8888)")
    parser.add_argument("--output", type=str, default="heart_recording.wav",
                        help="Output WAV filename")
    parser.add_argument("--duration", type=int, default=None,
                        help="Max recording seconds (default: unlimited)")
    parser.add_argument("--no-playback", action="store_true",
                        help="Disable live audio playback")

    args = parser.parse_args()

    print("=" * 50)
    print("  ESP32 Stethoscope WiFi Receiver")
    print("=" * 50)
    print()

    receive_and_save(
        ip=args.ip,
        port=args.port,
        output_file=args.output,
        duration=args.duration,
        live=not args.no_playback
    )


if __name__ == "__main__":
    main()
