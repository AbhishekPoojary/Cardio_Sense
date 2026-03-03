# Fix: No Sound & Live Diagnosis Not Detecting

## Problems Fixed ✅

### 1. **Port Mismatch** 
- ❌ **Was**: Firmware connected to port **8765** (wrong - that's for the Python receiver)
- ✅ **Now**: Firmware connects to port **8888** (WebSocket bridge for live diagnosis)

### 2. **Audio Format Mismatch**
- ❌ **Was**: Sending CRC16-framed binary packets (browser can't decode)
- ✅ **Now**: Sending raw int16 audio samples (browser expects this)

### 3. **Speaker Volume Too Low**
- ❌ **Was**: Speaker output capped at ±15,000 (quiet)
- ✅ **Now**: Added `SPEAKER_GAIN = 2.0` to boost volume

---

## Prerequisites

1. **Python WebSocket Bridge Running**
```bash
cd C:\Users\ABHISHEK\Desktop\Cardio_Sense
python esp32_ws_bridge.py
```

Should show:
```
TCP server listening on :8888 for ESP32
WebSocket server at ws://localhost:8765/ for browser
```

**Keep this running while using live diagnosis!**

2. **Flask App Running**
```bash
python app.py
```

3. **Hardware Checklist**
- [ ] ESP32 connected to laptop via USB (for serial/upload)
- [ ] Microphone connected to I2S pins (ICS-43434 → pin 33)
- [ ] Speaker connected to I2S pins (MAX98357A DIN → pin 26, GND, 5V)
- [ ] WiFi SSID "Nord5" with password "Abhishek1290"

---

## Upload & Test

### Step 1: Configure WiFi (OPTIONAL - only if using different network)
Edit `esp32_stethoscope_improved.ino` line 3-4:
```cpp
const char* WIFI_SSID     = "YourWiFiName";
const char* WIFI_PASSWORD = "YourPassword";
```

### Step 2: Upload to ESP32
- Open in Arduino IDE
- Select **Board: ESP32 Dev Module**
- Select **COM port** where ESP32 is attached
- Click **Upload**

### Step 3: Open Serial Monitor (115200 baud)
You should see:
```
Connecting to WiFi...
Connected! IP: 192.168.x.x
=== Stethoscope WiFi Streamer (IMPROVED) ===
...
[Ready, press button to stream]
```

### Step 4: Open Live Diagnosis

**In browser:**
1. Go to `http://localhost:5000`
2. Click **"Diagnose"** tab
3. Select **"Mode: Stethoscope"** 
4. Select **"Source: ESP32"** (this connects to WebSocket bridge on port 8765)
5. Click **"START"**

Should show:
- `✅ Connected to ESP32 bridge.`
- Waveform updating in real-time (green ECG line)

### Step 5: Test Speaker Sound

**Press GPIO4 button on ESP32** (or send 'S' over serial)

Should hear:
- ✅ Heartbeat sounds playing through speaker
- ✅ Waveform drawing on screen
- ✅ BPM detection running

---

## Troubleshooting

### Problem: "Could not connect to Python backend" error

**Fix**: 
```bash
# Make sure bridge is running
python esp32_ws_bridge.py

# If port 8888 is in use:
netstat -ano | find "8888"
# Kill the process and retry
```

### Problem: No waveform appearing

**Check**:
1. Bridge showing `✅ ESP32 connected`?
2. ESP32 button pressed to start streaming?
3. Check ESP32 serial monitor for errors
4. Try `SPEAKER_GAIN = 3.0` (louder) if still no sound

### Problem: Sound is very quiet

**Increase speaker gain** in `.ino`:
```cpp
#define SPEAKER_GAIN   3.0f  // Was 2.0, try 2.5-4.0
```

Re-upload and test.

### Problem: Sound is very distorted/clipping

**Decrease speaker gain**:
```cpp
#define SPEAKER_GAIN   1.5f  // Try lower values
```

---

## Network Topology

```
ESP32 (192.168.x.x)
   ↓ WiFi TCP
   Laptop (10.116.198.147:8888) ← WebSocket Bridge listens here
   ↑ 
Browser (ws://localhost:8765) ← Browser connects here
```

**Note**: If your laptop IP is different from `10.116.198.147`, update the ESP32 code:
```cpp
if (client.connect("YOUR_LAPTOP_IP", SERVER_PORT)) {
```

To find your laptop IP:
```bash
ipconfig
# Look for "IPv4 Address: 10.x.x.x" or "192.168.x.x"
```

---

## Key Changes Made

| Item | Before | After |
|------|--------|-------|
| **Port** | 8765 | 8888 (WebSocket bridge) |
| **Format** | CRC16-framed packets | Raw int16 audio |
| **Speaker Gain** | 1.0× | 2.0× (configurable) |
| **Output** | Capped at ±15,000 | Boosts to ±32,767 |

---

## Remote Recording (Optional)

If you want to also save audio recordings separately:
```bash
# Run this in a second terminal
python esp32_receiver_improved.py

# This listens on port 8765 (separate from WebSocket bridge)
# Creates timestamped WAV files automatically
```

But **for live diagnosis, only use the WebSocket bridge**.

---

## Still Having Issues?

Check the serial output for:
```
BPM: XX.X | Env: XXXX | RMS: XXXX | Thresh: XXXX | Stream: XXs
```

- **Env** should be > 300 when heartbeat is near mic
- **RMS** should track around 8000
- **Stream** should show packet count increasing

If these don't update, the DSP chain isn't processing audio correctly.
