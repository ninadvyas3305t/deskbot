#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <Arduino.h>

// DeskBot Hardware-Companion Framed Protocol Specification v2.0
// All event messages are framed as [EVENT:<TYPE>:<PARAMS>] on dedicated lines.
// This enables reliable streaming separation between raw audio bytes and structured control events.

namespace Protocol {

inline void sendDeviceReady(const char* version, const char* board, bool hasPsram, uint32_t flashMb) {
    Serial.printf("\n[EVENT:DEVICE_READY:version=%s:board=%s:psram=%s:flash=%uMB]\n",
                  version, board, hasPsram ? "true" : "none", flashMb);
    Serial.flush();
}

inline void sendWakeDetected(float confidence, uint32_t latencyMicros) {
    Serial.printf("\n[EVENT:WAKE_DETECTED:confidence=%.3f:latency_ms=%.1f]\n",
                  confidence, (float)latencyMicros / 1000.0f);
    Serial.flush();
}

inline void sendCommandClassified(const char* commandName, float confidence, uint32_t latencyMicros) {
    Serial.printf("\n[EVENT:COMMAND_CLASSIFIED:action=%s:confidence=%.3f:latency_ms=%.1f]\n",
                  commandName, confidence, (float)latencyMicros / 1000.0f);
    Serial.flush();
}

inline void sendUnrestrictedSpeech(float confidence) {
    Serial.printf("\n[EVENT:UNRESTRICTED_SPEECH:confidence=%.3f]\n", confidence);
    Serial.flush();
}

inline void sendTouchTrigger() {
    Serial.print("\n[EVENT:TOUCH_TRIGGER:action=tap]\n");
    Serial.flush();
}

inline void sendStatus(const char* stateName, uint32_t freeHeap, uint32_t uptimeSeconds) {
    Serial.printf("\n[EVENT:STATUS:state=%s:heap=%u:uptime_s=%u]\n",
                  stateName, freeHeap, uptimeSeconds);
    Serial.flush();
}

inline void sendHeartbeat(uint32_t seq, uint32_t uptimeMs) {
    Serial.printf("\n[EVENT:HEARTBEAT:seq=%u:uptime_ms=%u]\n", seq, uptimeMs);
    Serial.flush();
}

inline void sendAudioStreamStart() {
    Serial.print("\n[EVENT:AUDIO_START]\n");
    Serial.flush();
}

inline void sendAudioStreamEnd() {
    Serial.print("\n[EVENT:AUDIO_END]\n");
    Serial.flush();
}

inline void sendError(const char* errCode, const char* message) {
    Serial.printf("\n[EVENT:ERROR:code=%s:msg=%s]\n", errCode, message);
    Serial.flush();
}

} // namespace Protocol

#endif // PROTOCOL_H
