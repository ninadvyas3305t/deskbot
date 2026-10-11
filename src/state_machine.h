#ifndef STATE_MACHINE_H
#define STATE_MACHINE_H

#include <Arduino.h>

enum DeviceHardwareState {
    DEV_STATE_IDLE,
    DEV_STATE_WAKE_DETECTED,
    DEV_STATE_COMMAND_CAPTURE,
    DEV_STATE_WAITING_COMPANION,
    DEV_STATE_PROCESSING,
    DEV_STATE_SPEAKING,
    DEV_STATE_ERROR
};

class DeviceStateMachine {
public:
    DeviceStateMachine();

    DeviceHardwareState getCurrentState() const { return currentState; }
    const char* getStateName() const;

    void transitionTo(DeviceHardwareState newState, const char* reason = nullptr);
    void update();

    // Check if state has timed out (e.g. waiting for companion too long)
    bool isTimedOut() const;

    // Reset state to IDLE
    void resetToIdle();

private:
    DeviceHardwareState currentState;
    DeviceHardwareState previousState;
    uint32_t stateEnteredTime;
    uint32_t timeoutDurationMs;
};

#endif // STATE_MACHINE_H
