"""Continuous DeskBot voice assistant engine with rolling PCM buffer and explicit state machine."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np

# Ensure companion package directory is in sys.path
COMPANION_DIR = Path(__file__).resolve().parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

import config
from ai_brain import fast_intent_match, understand_intent
from assistant.context import ConversationContext
from assistant.state_machine import AssistantState, AssistantStateMachine
from audio.audio_engine import AudioEngine
from audio.speech_detector import SpeechDetector
from command_executor import ToolResult, execute_intent, get_action_description
from speech_to_text import get_whisper_model, transcribe, validate_audio
from tts import speak
from wake_word import create_model

logger = logging.getLogger("deskbot")



def save_wav(audio_bytes: bytes, output_path: Path = config.COMMAND_AUDIO_PATH) -> None:
    """Save raw 16kHz 16-bit mono PCM bytes to WAV format."""
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(config.CHANNELS)
        wav_file.setsampwidth(config.SAMPLE_WIDTH)
        wav_file.setframerate(config.SAMPLE_RATE)
        wav_file.writeframes(audio_bytes)


def run_assistant(
    port: str = config.DEFAULT_PORT,
    baud: int = config.DEFAULT_BAUD,
    wake_model: str = config.DEFAULT_WAKE_MODEL,
    wake_threshold: float = config.DEFAULT_WAKE_THRESHOLD,
    stt_model: str = config.DEFAULT_STT_MODEL,
    conversation_timeout: float = config.CONVERSATION_TIMEOUT_SECONDS,
    max_context_messages: int = config.MAX_CONTEXT_MESSAGES,
    context_ttl: float = config.CONTEXT_TTL_SECONDS,
    mic_gain: float = config.DEFAULT_MIC_GAIN,
    run_once: bool = False,
    debug: bool = False,
) -> int:
    """Run DeskBot continuous voice assistant loop with multi-turn active conversation."""
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    state_machine = AssistantStateMachine(wake_word_name="Hey Jarvis", debug=debug)

    print("Loading wake-word model...", flush=True)
    wake_detector, label = create_model(wake_model)

    get_whisper_model(stt_model)

    print(f"DeskBot ready. Listening for {wake_model}.", flush=True)

    speech_detector = SpeechDetector(
        sample_rate=config.SAMPLE_RATE,
        sample_width=config.SAMPLE_WIDTH,
        frame_duration_ms=config.FRAME_DURATION_MS,
        vad_mode=config.VAD_MODE,
        pre_roll_seconds=config.PRE_ROLL_SECONDS,
        silence_duration_seconds=config.SILENCE_DURATION_SECONDS,
        initial_speech_timeout=config.INITIAL_SPEECH_TIMEOUT,
        max_command_seconds=config.MAX_COMMAND_SECONDS,
        transition_window_seconds=config.TRANSITION_WINDOW_SECONDS,
    )

    audio_engine = AudioEngine(
        port=port,
        baud=baud,
        sample_rate=config.SAMPLE_RATE,
        sample_width=config.SAMPLE_WIDTH,
        frame_bytes=speech_detector.frame_bytes,
        ring_buffer_duration=2.0,
    )

    # Wire ESP32 OLED state broadcaster across active serial connection
    def broadcast_state(st: AssistantState) -> None:
        try:
            audio_engine.send_command(f"STATE_{st.value}")
        except Exception as b_err:
            if debug:
                logger.debug("OLED face broadcast error: %s", b_err)

    state_machine.set_state_broadcaster(broadcast_state)

    try:
        audio_engine.start()
    except Exception as start_err:
        state_machine.log("ERROR", f"Failed to start audio engine: {start_err}")
        return 1

    conversation_context = ConversationContext(
        max_messages=max_context_messages,
        ttl_seconds=context_ttl,
    )

    # openWakeWord processes audio in native 80ms windows (1280 samples * 2 bytes = 2560 bytes)
    WAKE_CHUNK_BYTES = 2560
    wake_pcm_buffer = bytearray()

    def reset_wake_scores() -> None:
        """Clear recent scores without wiping out openWakeWord audio feature spectrogram history."""
        wake_pcm_buffer.clear()
        if hasattr(wake_detector, "prediction_buffer") and label in wake_detector.prediction_buffer:
            wake_detector.prediction_buffer[label].clear()
            for _ in range(5):
                wake_detector.prediction_buffer[label].append(0.0)

    def process_utterance(initial_pcm: bytes) -> bool:
        """Transcribe, interpret with context, execute tool, confirm fuzzy deletions, and handle follow-up."""
        current_pcm: Optional[bytes] = initial_pcm

        while current_pcm:
            save_wav(current_pcm, config.COMMAND_AUDIO_PATH)
            validate_audio(config.COMMAND_AUDIO_PATH)

            state_machine.transition_to(AssistantState.TRANSCRIBING)
            transcript, _lang = transcribe(config.COMMAND_AUDIO_PATH, model_name=stt_model)

            if not transcript or not transcript.strip():
                state_machine.log("STT", "Could not transcribe audio.")
                state_machine.transition_to(AssistantState.IDLE)
                return False

            clean_transcript = transcript.strip()
            state_machine.on_transcript(clean_transcript)

            # Fast-path deterministic intent check (zero cloud latency for local utilities, time, screenshots, files)
            intent = fast_intent_match(clean_transcript)

            if not intent:
                # AI Thinking with bounded conversation context for general knowledge & open-ended queries
                state_machine.transition_to(AssistantState.THINKING)
                context_prompt = conversation_context.get_context_for_prompt()
                intent = understand_intent(clean_transcript, context_prompt=context_prompt)

            if not intent:
                state_machine.log("AI", "Could not determine intent.")
                msg = "Could not determine intent."
                if config.TTS_ENABLED:
                    state_machine.transition_to(AssistantState.SPEAKING, context=msg)
                    try:
                        speak(msg, block=True)
                    except Exception as tts_err:
                        logger.warning("TTS speech error: %s", tts_err)
                    audio_engine.drain_frames()
                    if hasattr(audio_engine.ring_buffer, "clear"):
                        audio_engine.ring_buffer.clear()
                    reset_wake_scores()

                conversation_context.add_turn(
                    user_speech=clean_transcript,
                    tool_name="unknown",
                    tool_query=None,
                    tool_success=False,
                    assistant_response=msg,
                )
                state_machine.transition_to(AssistantState.IDLE)
                return True

            action = intent.get("action", "unknown")
            query = intent.get("response") if "response" in intent else intent.get("query")
            state_machine.on_ai_action(action)

            if action == "direct_answer":
                spoken_response = str(query or "")
                state_machine.on_direct_answer(spoken_response)
                result = ToolResult(True, "Direct answer", spoken_response)
            else:
                action_desc = get_action_description(intent)
                state_machine.transition_to(AssistantState.EXECUTING, context=action_desc)
                result = execute_intent(intent)
                state_machine.on_tool(action, result.success, result.message)
                spoken_response = result.response_text or result.message

                if result.response_text:
                    state_machine.on_response(result.response_text)

            # Destructive file confirmation handling
            if (
                result.data
                and isinstance(result.data, dict)
                and result.data.get("confirmation_required")
                and result.data.get("action") == "delete_file"
            ):
                target_path_str = result.data.get("target_path", "")
                display_name = result.data.get("display_name", Path(target_path_str).name)
                conf_prompt = spoken_response

                if config.TTS_ENABLED and conf_prompt:
                    state_machine.transition_to(AssistantState.SPEAKING, context=conf_prompt)
                    try:
                        speak(conf_prompt, block=True)
                    except Exception as tts_err:
                        logger.warning("TTS speech error: %s", tts_err)
                    audio_engine.drain_frames()
                    if hasattr(audio_engine.ring_buffer, "clear"):
                        audio_engine.ring_buffer.clear()
                    reset_wake_scores()

                state_machine.on_confirmation(conf_prompt)
                conf_pcm = speech_detector.capture_utterance(
                    read_frame_fn=lambda: audio_engine.read_frame(timeout=0.5),
                    ring_buffer=audio_engine.ring_buffer,
                    on_speech_start=state_machine.on_speech_start,
                    on_speech_end=state_machine.on_speech_end,
                    initial_timeout=7.0,
                    in_wake_transition=False,
                )

                if not conf_pcm:
                    timeout_msg = "Confirmation timed out. I won't delete it."
                    if config.TTS_ENABLED:
                        state_machine.transition_to(AssistantState.SPEAKING, context=timeout_msg)
                        speak(timeout_msg, block=True)
                        audio_engine.drain_frames()
                        reset_wake_scores()
                    conversation_context.add_turn(
                        user_speech=clean_transcript,
                        tool_name=action,
                        tool_query=str(query) if query is not None else None,
                        tool_success=False,
                        assistant_response=timeout_msg,
                    )
                else:
                    save_wav(conf_pcm, config.COMMAND_AUDIO_PATH)
                    conf_text, _ = transcribe(config.COMMAND_AUDIO_PATH, model_name=stt_model)
                    conf_clean = (conf_text or "").strip().lower().strip(".,?!;:`'\"")
                    state_machine.on_transcript(conf_clean)

                    is_yes = conf_clean in {"yes", "yeah", "yup", "yep", "sure", "confirm", "go ahead", "do it", "delete it", "yes delete it", "please do"}
                    is_no = conf_clean in {"no", "nope", "nah", "cancel", "don't", "dont", "stop", "nevermind", "keep it"}

                    if is_yes:
                        from tools.file_tools import execute_pending_deletion
                        del_res = execute_pending_deletion(target_path_str)
                        del_msg = del_res.response_text or f"Deleted {display_name}."
                        state_machine.on_response(del_msg)
                        if config.TTS_ENABLED:
                            state_machine.transition_to(AssistantState.SPEAKING, context=del_msg)
                            speak(del_msg, block=True)
                            audio_engine.drain_frames()
                            reset_wake_scores()
                        conversation_context.add_turn(
                            user_speech=clean_transcript,
                            tool_name=action,
                            tool_query=str(query) if query is not None else None,
                            tool_success=True,
                            assistant_response=del_msg,
                        )
                    elif is_no:
                        no_msg = f"Okay, I won't delete {display_name}."
                        state_machine.on_response(no_msg)
                        if config.TTS_ENABLED:
                            state_machine.transition_to(AssistantState.SPEAKING, context=no_msg)
                            speak(no_msg, block=True)
                            audio_engine.drain_frames()
                            reset_wake_scores()
                        conversation_context.add_turn(
                            user_speech=clean_transcript,
                            tool_name=action,
                            tool_query=str(query) if query is not None else None,
                            tool_success=False,
                            assistant_response=no_msg,
                        )
                    else:
                        current_pcm = conf_pcm
                        continue
            else:
                # Standard spoken response
                if config.TTS_ENABLED and spoken_response:
                    state_machine.transition_to(AssistantState.SPEAKING, context=spoken_response)
                    try:
                        speak(spoken_response, block=True)
                    except Exception as tts_err:
                        logger.warning("TTS speech error: %s", tts_err)
                    audio_engine.drain_frames()
                    if hasattr(audio_engine.ring_buffer, "clear"):
                        audio_engine.ring_buffer.clear()
                    reset_wake_scores()

                conversation_context.add_turn(
                    user_speech=clean_transcript,
                    tool_name=action,
                    tool_query=str(query) if query is not None else None,
                    tool_success=result.success,
                    assistant_response=spoken_response,
                )

            # Post-Command Conversational Confirmation: "Is that all?"
            follow_up_prompt = "Is that all?"
            state_machine.on_follow_up(follow_up_prompt)

            if config.TTS_ENABLED:
                try:
                    speak(follow_up_prompt, block=True)
                except Exception as tts_err:
                    logger.warning("TTS speech error: %s", tts_err)
                audio_engine.drain_frames()
                if hasattr(audio_engine.ring_buffer, "clear"):
                    audio_engine.ring_buffer.clear()
                reset_wake_scores()

            fu_pcm = speech_detector.capture_utterance(
                read_frame_fn=lambda: audio_engine.read_frame(timeout=0.5),
                ring_buffer=audio_engine.ring_buffer,
                on_speech_start=state_machine.on_speech_start,
                on_speech_end=state_machine.on_speech_end,
                initial_timeout=7.0,
                in_wake_transition=False,
            )

            if not fu_pcm:
                standby_msg = "Going back to standby."
                state_machine.log("FOLLOW_UP", "Timeout: Going back to standby.")
                if config.TTS_ENABLED:
                    state_machine.transition_to(AssistantState.SPEAKING, context=standby_msg)
                    speak(standby_msg, block=True)
                    audio_engine.drain_frames()
                    reset_wake_scores()
                state_machine.transition_to(AssistantState.IDLE)
                return True

            save_wav(fu_pcm, config.COMMAND_AUDIO_PATH)
            fu_text, _ = transcribe(
                config.COMMAND_AUDIO_PATH,
                model_name=stt_model,
            )
            fu_clean = (fu_text or "").strip()

            if not fu_clean:
                # If audio was captured but speech wasn't decoded, ask once before going to standby
                retry_prompt = "Could you repeat that?"
                state_machine.log("FOLLOW_UP", f'Asking "{retry_prompt}"')
                if config.TTS_ENABLED:
                    state_machine.transition_to(AssistantState.SPEAKING, context=retry_prompt)
                    try:
                        speak(retry_prompt, block=True)
                    except Exception as tts_err:
                        logger.warning("TTS speech error: %s", tts_err)
                    audio_engine.drain_frames()
                    audio_engine.clear_touch()
                    if hasattr(audio_engine.ring_buffer, "clear"):
                        audio_engine.ring_buffer.clear()
                    reset_wake_scores()

                state_machine.transition_to(AssistantState.FOLLOW_UP)
                retry_pcm = speech_detector.capture_utterance(
                    read_frame_fn=lambda: audio_engine.read_frame(timeout=0.5),
                    ring_buffer=audio_engine.ring_buffer,
                    on_speech_start=state_machine.on_speech_start,
                    on_speech_end=state_machine.on_speech_end,
                    initial_timeout=5.0,
                    in_wake_transition=False,
                )
                if retry_pcm:
                    save_wav(retry_pcm, config.COMMAND_AUDIO_PATH)
                    fu_text, _ = transcribe(
                        config.COMMAND_AUDIO_PATH,
                        model_name=stt_model,
                    )
                    fu_clean = (fu_text or "").strip()

            if not fu_clean:
                standby_msg = "Going back to standby."
                state_machine.log("FOLLOW_UP", "Timeout: Going back to standby.")
                if config.TTS_ENABLED:
                    state_machine.transition_to(AssistantState.SPEAKING, context=standby_msg)
                    speak(standby_msg, block=True)
                    audio_engine.drain_frames()
                    audio_engine.clear_touch()
                    reset_wake_scores()
                state_machine.transition_to(AssistantState.IDLE)
                return True

            state_machine.on_transcript(fu_clean)
            fu_lower = fu_clean.lower().replace(",", " ").strip(".,?!;:`'\"")
            fu_lower = re.sub(r"\s+", " ", fu_lower).strip()
            fu_words = fu_lower.split()

            AFFIRMATIVE_RESPONSES = {
                "yes", "yeah", "yup", "yep", "sure", "that's all", "thats all",
                "that is all", "i'm good", "im good", "no more", "all good",
                "that's it", "thats it", "that is it", "all done", "done",
                "nothing else", "nothing", "nope that's all", "no that's all",
                "alright", "thank you", "thanks", "that'll do", "that will do",
                "no that's it", "no thats it", "that would be all", "fine",
                "no that is all", "no thank you", "no thanks", "good", "all set",
            }

            NEGATIVE_STANDALONE = {
                "no", "nope", "nah", "not yet", "wait", "hold on", "one more thing",
                "not really", "wait a minute", "hang on",
            }

            is_affirmative = (
                fu_lower in AFFIRMATIVE_RESPONSES
                or (fu_words and all(w in {"yes", "yeah", "yup", "yep", "sure", "ok", "okay", "done", "fine", "good"} for w in fu_words))
                or any(phrase in fu_lower for phrase in {"that's all", "thats all", "all done", "that's it", "thats it", "nothing else", "no more", "im good", "i'm good", "all set"})
            )

            is_negative = (
                fu_lower in NEGATIVE_STANDALONE
                or (fu_words and all(w in {"no", "nope", "nah"} for w in fu_words))
            )

            if is_affirmative:
                done_msg = "Alright."
                if config.TTS_ENABLED:
                    state_machine.transition_to(AssistantState.SPEAKING, context=done_msg)
                    speak(done_msg, block=True)
                    audio_engine.drain_frames()
                    audio_engine.clear_touch()
                    reset_wake_scores()
                state_machine.transition_to(AssistantState.IDLE)
                return True

            elif is_negative:
                more_msg = "What else would you like me to do?"
                if config.TTS_ENABLED:
                    state_machine.transition_to(AssistantState.SPEAKING, context=more_msg)
                    speak(more_msg, block=True)
                    audio_engine.drain_frames()
                    reset_wake_scores()
                state_machine.transition_to(AssistantState.LISTENING)

                next_cmd_pcm = speech_detector.capture_utterance(
                    read_frame_fn=lambda: audio_engine.read_frame(timeout=0.5),
                    ring_buffer=audio_engine.ring_buffer,
                    on_speech_start=state_machine.on_speech_start,
                    on_speech_end=state_machine.on_speech_end,
                    initial_timeout=7.0,
                    in_wake_transition=False,
                )
                if next_cmd_pcm:
                    current_pcm = next_cmd_pcm
                    continue
                else:
                    standby_msg = "Going back to standby."
                    if config.TTS_ENABLED:
                        state_machine.transition_to(AssistantState.SPEAKING, context=standby_msg)
                        speak(standby_msg, block=True)
                        audio_engine.drain_frames()
                        reset_wake_scores()
                    state_machine.transition_to(AssistantState.IDLE)
                    return True

            else:
                # Direct new command (e.g. "No, open my project" or "Play Tame Impala")
                current_pcm = fu_pcm
                continue

        state_machine.transition_to(AssistantState.IDLE)
        return True

    state_machine.transition_to(AssistantState.IDLE)

    try:
        while True:
            # Check TTP223 hardware touch sensor trigger (push-to-talk from IDLE)
            if audio_engine.check_and_consume_touch():
                state_machine.on_touch()
                audio_engine.clear_touch()
                captured_pcm = speech_detector.capture_utterance(
                    read_frame_fn=lambda: audio_engine.read_frame(timeout=0.5),
                    ring_buffer=audio_engine.ring_buffer,
                    on_speech_start=state_machine.on_speech_start,
                    on_speech_end=state_machine.on_speech_end,
                    initial_timeout=7.0,
                    in_wake_transition=False,
                )
                if not captured_pcm:
                    state_machine.log("LISTENING", "No valid speech detected.")
                    audio_engine.drain_frames()
                    audio_engine.clear_touch()
                    reset_wake_scores()
                    state_machine.transition_to(AssistantState.IDLE)
                    if run_once:
                        return 0
                    continue

                try:
                    process_utterance(captured_pcm)
                except Exception as cmd_error:
                    state_machine.handle_error_and_recover(f"Command processing error: {cmd_error}")
                    state_machine.transition_to(AssistantState.IDLE)

                if run_once:
                    return 0

                audio_engine.drain_frames()
                audio_engine.clear_touch()
                reset_wake_scores()
                continue

            # Standby Wake-Word Detection
            frame = audio_engine.read_frame(timeout=0.5)
            if not frame:
                continue

            wake_pcm_buffer.extend(frame)
            if len(wake_pcm_buffer) < WAKE_CHUNK_BYTES:
                continue

            detected = False
            detected_score = 0.0

            while len(wake_pcm_buffer) >= WAKE_CHUNK_BYTES:
                chunk_bytes = bytes(wake_pcm_buffer[:WAKE_CHUNK_BYTES])
                del wake_pcm_buffer[:WAKE_CHUNK_BYTES]

                audio_array = np.frombuffer(chunk_bytes, dtype=np.int16)
                if mic_gain != 1.0:
                    audio_array = np.clip(
                        audio_array.astype(np.float32) * mic_gain,
                        -32768,
                        32767,
                    ).astype(np.int16)

                prediction = wake_detector.predict(audio_array)
                score = prediction.get(label, 0.0)

                if score >= wake_threshold:
                    detected = True
                    detected_score = score
                    break

            if not detected:
                continue

            # Wake Word Detected
            state_machine.on_wake(detected_score)
            reset_wake_scores()

            try:
                captured_pcm = speech_detector.capture_utterance(
                    read_frame_fn=lambda: audio_engine.read_frame(timeout=0.5),
                    ring_buffer=audio_engine.ring_buffer,
                    on_speech_start=state_machine.on_speech_start,
                    on_speech_end=state_machine.on_speech_end,
                )

                if not captured_pcm:
                    state_machine.log("LISTENING", "No valid speech detected.")
                    audio_engine.drain_frames()
                    reset_wake_scores()
                    state_machine.transition_to(AssistantState.IDLE)
                    if run_once:
                        return 0
                    continue

                process_utterance(captured_pcm)

            except Exception as cmd_error:
                state_machine.handle_error_and_recover(f"Command processing error: {cmd_error}")
                state_machine.transition_to(AssistantState.IDLE)

            if run_once:
                return 0

            audio_engine.drain_frames()
            reset_wake_scores()

    except KeyboardInterrupt:
        print("\nDeskBot stopped by user.", flush=True)
        return 0
    finally:
        audio_engine.stop()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run DeskBot continuously: wake word, command, action, standby."
    )
    parser.add_argument("--port", default=config.DEFAULT_PORT, help=f"Serial port (default: {config.DEFAULT_PORT})")
    parser.add_argument("--baud", type=int, default=config.DEFAULT_BAUD, help=f"Baud rate (default: {config.DEFAULT_BAUD})")
    parser.add_argument("--wake-model", default=config.DEFAULT_WAKE_MODEL, help=f"Wake model (default: {config.DEFAULT_WAKE_MODEL})")
    parser.add_argument(
        "--wake-threshold",
        type=float,
        default=config.DEFAULT_WAKE_THRESHOLD,
        help=f"Wake threshold (default: {config.DEFAULT_WAKE_THRESHOLD})",
    )
    parser.add_argument(
        "--stt-model",
        default=config.DEFAULT_STT_MODEL,
        help="Faster-Whisper model name.",
    )
    parser.add_argument(
        "--mic-gain",
        type=float,
        default=config.DEFAULT_MIC_GAIN,
        help=f"Software microphone gain multiplier (default: {config.DEFAULT_MIC_GAIN})",
    )
    parser.add_argument(
        "--conversation-timeout",
        type=float,
        default=config.CONVERSATION_TIMEOUT_SECONDS,
        help=f"Follow-up active conversation timeout in seconds (default: {config.CONVERSATION_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after one wake activation (for testing).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable detailed debug logging.",
    )
    args = parser.parse_args()

    if not 0 < args.wake_threshold <= 1:
        parser.error("--wake-threshold must be greater than 0 and no more than 1.")

    return run_assistant(
        port=args.port,
        baud=args.baud,
        wake_model=args.wake_model,
        wake_threshold=args.wake_threshold,
        stt_model=args.stt_model,
        conversation_timeout=args.conversation_timeout,
        mic_gain=args.mic_gain,
        run_once=args.once,
        debug=args.debug,
    )


if __name__ == "__main__":
    raise SystemExit(main())
