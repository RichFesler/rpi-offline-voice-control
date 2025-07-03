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
# 28JUN2025 - Added MQTT output, refactored for systemd use, rfesler@gmail.com
# 27JUN2025 - Initial version, integrated Vosk model support, rfesler@gmail.com

import os
import vosk
import sys
import json
import paho.mqtt.client as mqtt
import time

# --- MQTT Configuration ---
MQTT_BROKER_ADDRESS = "localhost"         # Hostname of MQTT broker (use IP if remote)
MQTT_PORT = 1883                          # Default MQTT port
MQTT_TOPIC_FINAL = "voice/final"          # Topic to publish final STT results
MQTT_TOPIC_PARTIAL = "voice/partial"      # Topic to publish partial (interim) results
MQTT_CLIENT_ID = "vosk_stt_client"        # MQTT client ID for tracking

# --- MQTT Setup ---
def on_connect(client, userdata, flags, rc):
    # Called on successful connection to MQTT broker
    print(f"MQTT connected with result code {rc}", file=sys.stderr)

def on_publish(client, userdata, mid):
    # Optional: Called after publishing a message
    pass

# --- Main Entry Point ---
if __name__ == "__main__":
    # Create MQTT client and assign callbacks
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_publish = on_publish

    # Connect to MQTT broker and start background thread
    client.connect(MQTT_BROKER_ADDRESS, MQTT_PORT, 60)
    client.loop_start()
    time.sleep(1)  # Give time for MQTT connection to establish

    # Verify that the Vosk model directory exists
    if not os.path.exists("vosk-model-small-en-us-0.15"):
        print("Missing Vosk model folder.", file=sys.stderr)
        sys.exit(1)

    # Load the Vosk STT model and create recognizer with 16kHz sample rate
    model = vosk.Model("vosk-model-small-en-us-0.15")
    rec = vosk.KaldiRecognizer(model, 16000)

    try:
        # Continuously read binary audio from stdin (e.g., from ffmpeg pipe)
        while True:
            data = sys.stdin.buffer.read(4096)  # 4KB buffer size
            if not data:
                break  # End of input stream

            # Process complete utterance
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if result['text']:  # Only publish non-empty results
                    client.publish(MQTT_TOPIC_FINAL, result['text'])
                    print(f"Final: {result['text']}")
            else:
                # Send partial result as user speaks
                partial = json.loads(rec.PartialResult())
                if partial['partial']:
                    client.publish(MQTT_TOPIC_PARTIAL, partial['partial'])
                    # Print partial output inline
                    sys.stdout.write(f"\rPartial: {partial['partial']} ".ljust(80))
                    sys.stdout.flush()

    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        pass
    finally:
        # Disconnect cleanly
        client.loop_stop()
        client.disconnect()
