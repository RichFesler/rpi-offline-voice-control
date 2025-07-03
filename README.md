## 🗣️ Raspberry Pi Voice Control System: Offline STT & Playback (Vosk, FFmpeg, MQTT, Node-RED)

This system enables fully offline voice recognition on a Raspberry Pi. It continuously listens for speech, transcribes it with the Vosk engine, and publishes results to MQTT for use in Node-RED. It also supports audio playback via the same USB speaker.

Tested on Raspberry Pi OS Bookworm 64-bit (headless) using the **KAYSUDA PC Microphone Speaker** (\~\$40 on Amazon).

---

## 💡 Features

- Continuous offline speech recognition using Vosk
- Publishes partial and final transcriptions to MQTT
- Headless and auto-starts via systemd
- Supports simultaneous mic input and audio playback
- MP3/WAV playback via mpg123 or aplay
- Fully offline and reliable under systemd

---

## 🛠️ Prerequisites

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    build-essential git ffmpeg mpg123 \
    libasound2-plugins \
    mosquitto mosquitto-clients \
    python3-venv python3-pip
sudo rpi-update
sudo usermod -aG audio <your_username>
sudo reboot
```

---

## 🔊 ALSA Configuration

```bash
sudo nano /etc/modprobe.d/alsa-base.conf
```

```ini
options snd-usb-audio index=0
options snd-bcm2835 index=1
```

```bash
sudo nano /etc/asound.conf
```

```ini
pcm.!default {
    type plug
    slave.pcm "hw:0,0"
}
```

```bash
sudo reboot
```

### 🔍 How to determine `hw:0,0`

Use the following command to list audio devices:

```bash
aplay -l
```

Look for a device labeled something like:

```
card 0: SP300U [SPEAKPHONE SP300U], device 0: USB Audio [USB Audio]
```

This means your device path is `hw:0,0`. If it's card 1 instead, use `hw:1,0` and update your config accordingly.

Device numbers can shift depending on which USB port the speaker is plugged into. If you're seeing device issues or errors like "No such device", try a different port or force device ordering in `alsa-base.conf` as shown above.

---

## 📦 Vosk + MQTT Setup (Python venv)

### Why use a venv?

Using a Python virtual environment isolates project dependencies like `vosk` and `paho-mqtt` from your system-wide Python. It ensures clean upgrades, fewer conflicts, and a reproducible install.

```bash
mkdir ~/vosk_pipe_stt
cd ~/vosk_pipe_stt
python3 -m venv venv
source venv/bin/activate
pip install vosk paho-mqtt
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip
```

---

## 🧠 pipe\_stt.py

```python
# Name: pipe_stt.py
#
# Description: Converts live audio input (via stdin) to text using Vosk STT engine.
#              Publishes partial and final transcription results to MQTT topics.
#              Designed to be used with piped audio input (e.g., from arecord).
#
# Input:
#   Raw 16kHz 16-bit mono audio via stdin (from arecord or ffmpeg)
#
# Output:
#   MQTT "voice/final"   - string: Final complete recognized phrase
#   MQTT "voice/partial" - string: Partial real-time phrase (optional)
#
# REVISIONS:
# 03JUL2025 - Final version, cleaned for GitHub release, rfesler@gmail.com

import os, vosk, sys, json, time
import paho.mqtt.client as mqtt

# MQTT connection settings
MQTT_BROKER_ADDRESS = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_FINAL = "voice/final"
MQTT_TOPIC_PARTIAL = "voice/partial"
MQTT_CLIENT_ID = "vosk_stt_client"
MODEL_PATH = "vosk-model-small-en-us-0.15"

# Callback when MQTT connects to the broker
def on_connect(client, userdata, flags, rc):
    print(f"MQTT connected with result code {rc}", file=sys.stderr)

# Setup MQTT client and connect
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=MQTT_CLIENT_ID)
client.on_connect = on_connect
client.connect(MQTT_BROKER_ADDRESS, MQTT_PORT, 60)
client.loop_start()
time.sleep(1)  # Allow time for MQTT connection to initialize

# Check if the Vosk model exists
if not os.path.exists(MODEL_PATH):
    print("Missing Vosk model folder.", file=sys.stderr)
    sys.exit(1)

# Load Vosk STT model and set 16kHz input
model = vosk.Model(MODEL_PATH)
rec = vosk.KaldiRecognizer(model, 16000)

try:
    # Process audio data from stdin
    while True:
        data = sys.stdin.buffer.read(4096)  # Read audio buffer in chunks
        if not data:
            break  # End of input

        if rec.AcceptWaveform(data):
            # Finalized result
            result = json.loads(rec.Result())
            if result['text']:
                client.publish(MQTT_TOPIC_FINAL, result['text'])
                print(f"Final: {result['text']}")
        else:
            # Interim result
            partial = json.loads(rec.PartialResult())
            if partial['partial']:
                client.publish(MQTT_TOPIC_PARTIAL, partial['partial'])
                sys.stdout.write(f"\rPartial: {partial['partial']} ".ljust(80))
                sys.stdout.flush()
except KeyboardInterrupt:
    # Graceful exit on Ctrl+C
    pass
finally:
    # Cleanup MQTT connection
    client.loop_stop()
    client.disconnect()
```

---

## ⚙️ systemd Auto-Start

```bash
sudo nano /etc/systemd/system/vosk-stt.service
```

```ini
[Unit]
Description=Vosk Speech-to-Text Service
After=network.target mosquitto.service
Requires=mosquitto.service

[Service]
User=<your_username>
Group=audio
WorkingDirectory=/home/<your_username>/vosk_pipe_stt
ExecStart=/bin/bash -c "/usr/bin/arecord -D plughw:0,0 -f S16_LE -r 16000 -c 1 | /home/<your_username>/vosk_pipe_stt/venv/bin/python /home/<your_username>/vosk_pipe_stt/pipe_stt.py"
Restart=always
RestartSec=5s
StandardOutput=journal
StandardError=journal
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=multi-user.target
```

```bash
sudo chmod o+rx /home/<your_username>
sudo chmod o+rx /home/<your_username>/vosk_pipe_stt
sudo systemctl daemon-reload
sudo systemctl enable vosk-stt.service
sudo systemctl start vosk-stt.service
```

---

## 🔄 Node-RED Playback Setup

- Inject Node → Payload: `/home/pi/audio/testaudio.mp3`
- Exec Node → Command: `mpg123 -a default -b 512`
- WAV Alternative: `aplay -D default -f S16_LE -r 48000 -c 2 -B 96000 -F 24000`
- Debug Node → capture `msg.payload`, `msg.stderr`, and `msg.rc`

---

## 🐛 Troubleshooting Summary

- 🔍 **Root Cause**: Playback failures were due to missing or invalid buffers. ALSA was receiving no usable stream and dropping the device.
- 🔄 Replaced PyAudio with arecord for input
- 💤 Added sleep or buffer tuning for device init under systemd
- 🎚️ Used speaker-test to confirm hardware worked
- 🧠 Applied buffer settings to aplay/mpg123 for stability
- 🎧 Enabled simultaneous mic input + audio playback

This configuration delivers a reliable, offline-capable voice interface for Raspberry Pi automation or embedded projects.

