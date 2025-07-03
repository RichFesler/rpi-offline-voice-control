🗣️ Raspberry Pi Voice Control System: Offline STT & Playback
(Vosk, FFmpeg, MQTT, Node-RED)

This system enables fully offline voice recognition on a Raspberry Pi. It continuously listens for speech, transcribes it with the Vosk engine, and publishes results to MQTT for use in Node-RED. It also supports audio playback via the same USB speaker.


## 💡 Features
- Continuous offline speech recognition using Vosk
- Publishes partial and final transcriptions to MQTT
- Headless and auto-starts via systemd
- Supports simultaneous mic input and audio playback
- MP3/WAV playback via mpg123 or aplay

Optimized for Raspberry Pi OS Bookworm

Tested with KAYSUDA USB Speaker/Microphone ($40 Amazon device)


## 🛠️ Prerequisites
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    build-essential git ffmpeg mpg123 \
    libasound2-plugins \
    mosquitto mosquitto-clients \
    python3-venv python3-pip
sudo rpi-update
sudo usermod -aG audio <your_username>
sudo reboot


## 🔊 ALSA Configuration
nano /etc/modprobe.d/alsa-base.conf
    options snd-usb-audio index=0
    options snd-bcm2835 index=1

nano /etc/asound.conf
    pcm.!default {
        type plug
        slave.pcm "hw:0,0"
    }

sudo reboot


## 📦 Vosk + MQTT Setup (Python venv)
Why use a venv?
Using a Python virtual environment isolates project dependencies like vosk and paho-mqtt from your system-wide Python. It ensures clean upgrades, fewer conflicts, and a reproducible install.

mkdir ~/vosk_pipe_stt
cd ~/vosk_pipe_stt
python3 -m venv venv
source venv/bin/activate
pip install vosk paho-mqtt
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip


## 🧠 pipe_stt.py

# Name: pipe_stt.py
#
# Description: Converts live audio input (via stdin) to text using Vosk STT engine.
#              Publishes partial and final transcription results to MQTT topics.
#              Designed to be used with piped audio input (e.g., from ffmpeg).
#
# Input:
#   Raw 16kHz 16-bit mono audio via stdin (from ffmpeg or arecord)
#
# Output:
#   MQTT "voice/final"   - string: Final complete recognized phrase
#   MQTT "voice/partial" - string: Partial real-time phrase (optional)
#
# REVISIONS:
# 03JUL2025 - Final version, cleaned for GitHub release, rfesler@gmail.com

import os, vosk, sys, json, time
import paho.mqtt.client as mqtt

MQTT_BROKER_ADDRESS = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_FINAL = "voice/final"
MQTT_TOPIC_PARTIAL = "voice/partial"
MQTT_CLIENT_ID = "vosk_stt_client"

def on_connect(client, userdata, flags, rc):
    print(f"MQTT connected with result code {rc}", file=sys.stderr)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=MQTT_CLIENT_ID)
client.on_connect = on_connect
client.connect(MQTT_BROKER_ADDRESS, MQTT_PORT, 60)
client.loop_start()
time.sleep(1)

if not os.path.exists("vosk-model-small-en-us-0.15"):
    print("Missing Vosk model folder.", file=sys.stderr)
    sys.exit(1)

model = vosk.Model("vosk-model-small-en-us-0.15")
rec = vosk.KaldiRecognizer(model, 16000)

try:
    while True:
        data = sys.stdin.buffer.read(4096)
        if not data:
            break
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            if result['text']:
                client.publish(MQTT_TOPIC_FINAL, result['text'])
                print(f"Final: {result['text']}")
        else:
            partial = json.loads(rec.PartialResult())
            if partial['partial']:
                client.publish(MQTT_TOPIC_PARTIAL, partial['partial'])
                sys.stdout.write(f"\rPartial: {partial['partial']} ".ljust(80))
                sys.stdout.flush()
except KeyboardInterrupt:
    pass
finally:
    client.loop_stop()
    client.disconnect()


## ⚙️ systemd Auto-Start
Create:
nano /etc/systemd/system/vosk-stt.service

[Unit]
Description=Vosk Speech-to-Text Service
After=network.target mosquitto.service
Requires=mosquitto.service

[Service]
User=<your_username>
Group=audio
WorkingDirectory=/home/<your_username>/vosk_pipe_stt
ExecStart=/bin/bash -c "sleep 5 && ffmpeg -f alsa -i plughw:0,0 -acodec pcm_s16le -ar 16000 -ac 1 -f s16le - | /home/<your_username>/vosk_pipe_stt/venv/bin/python pipe_stt.py"
Restart=always
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
Enable it:

sudo chmod o+rx /home/<your_username>
sudo chmod o+rx /home/<your_username>/vosk_pipe_stt
sudo systemctl daemon-reload
sudo systemctl enable vosk-stt.service
sudo systemctl start vosk-stt.service


## 🔄 Node-RED Playback Setup
Inject Node → Payload: /home/pi/audio/testaudio.mp3

Exec Node → mpg123 -a default -b 512

Or for WAV: aplay -D default -f S16_LE -r 48000 -c 2 -B 96000 -F 24000

Debug Node → capture msg.payload, msg.stderr, and msg.rc


## 🐛 Debugging Tools

mosquitto_sub -h localhost -t "voice/#" -v


## 🧠 Troubleshooting Summary
Real root cause: Playback failures were due to missing or invalid buffers. ALSA was receiving no usable stream and dropping the device.

* Replaced PyAudio with ffmpeg to pipe audio directly.
* Added sleep to give ffmpeg/mic time to initialize under systemd.
* Used speaker-test to validate playback and debug ALSA behavior.
* aplay and mpg123 needed buffer/period settings to stabilize playback.
* Now handles mic input and audio output concurrently without issues.
