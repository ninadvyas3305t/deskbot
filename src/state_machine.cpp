#include "state_machine.h"

DeviceStateMachine::DeviceStateMachine()
    : currentState(DEV_STATE_IDLE),
      previousState(DEV_STATE_IDLE),
      stateEnteredTime(0),
      timeoutDurationMs(0) {
}

const char* DeviceStateMachine::getStateName() const {
    switch (currentState) {
        case DEV_STATE_IDLE:              return "IDLE";
        case DEV_STATE_WAKE_DETECTED:     return "WAKE_DETECTED";
        case DEV_STATE_COMMAND_CAPTURE:   return "COMMAND_CAPTURE";
        case DEV_STATE_WAITING_COMPANION: return "WAITING_COMPANION";
        case DEV_STATE_PROCESSING:        return "PROCESSING";
        case DEV_STATE_SPEAKING:          return "SPEAKING";
        case DEV_STATE_ERROR:             return "ERROR";
        default:                          return "UNKNOWN";
    }
}

void DeviceStateMachine::transitionTo(DeviceHardwareState newState, const char* reason) {
    if (currentState == newState) {
        return;
    }

    previousState = currentState;
    currentState = newState;
    stateEnteredTime = millis();

    // Configure appropriate watchdog timeouts for states
    switch (newState) {
        case DEV_STATE_WAKE_DETECTED:
            timeoutDurationMs = 1200; // 1.2s auto-transition to COMMAND_CAPTURE
            break;
        case DEV_STATE_COMMAND_CAPTURE:
            timeoutDurationMs = 8000; // 8s max command capture
            break;
        case DEV_STATE_WAITING_COMPANION:
            timeoutDurationMs = 15000; // 15s companion timeout before auto-idle
            break;
        case DEV_STATE_PROCESSING:
            timeoutDurationMs = 25000; // 25s processing timeout
            break;
        case DEV_STATE_SPEAKING:
            timeoutDurationMs = 30000; // 30s speaking timeout
            break;
        case DEV_STATE_ERROR:
            timeoutDurationMs = 3000; // 3s error auto-recovery
            break;
        default:
            timeoutDurationMs = 0; // IDLE has no timeout
            break;
    }
}

bool DeviceStateMachine::isTimedOut() const {
    if (timeoutDurationMs == 0) {
        return false;
    }
    return (millis() - stateEnteredTime) > timeoutDurationMs;
}

void DeviceStateMachine::resetToIdle() {
    transitionTo(DEV_STATE_IDLE, "Reset");
}

void DeviceStateMachine::update() {
    if (isTimedOut()) {
        if (currentState == DEV_STATE_WAKE_DETECTED) {
            transitionTo(DEV_STATE_COMMAND_CAPTURE, "Wake delay complete");
        } else if (currentState == DEV_STATE_ERROR ||
                   currentState == DEV_STATE_WAITING_COMPANION ||
                   currentState == DEV_STATE_COMMAND_CAPTURE) {
            transitionTo(DEV_STATE_IDLE, "State watchdog timeout auto-recovery");
        }
    }
}
