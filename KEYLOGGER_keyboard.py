"""
KEYLOGGER_keyboard_buffered_threaded.py
---------------------------------------
Keyboard-based typing cadence logger using the low-level `keyboard` library.
Now uses a threaded queue processor for near-zero event loss even at high typing speeds.
Stores all data in memory first (buffer), then writes to CSV at the end.
"""

import time
import csv
import os
import threading
from datetime import datetime
from queue import Queue
import keyboard  # pip install keyboard

# -------------------------
# CONFIG
# -------------------------
TARGET_PHRASE = "Football123 player"
NUM_ATTEMPTS = 5
OUTPUT_CSV = "Test_FILE_BUFFERED_THREADED.csv"
REQUIRE_ENTER_TO_START = True

# -------------------------
# OUTPUT HEADER
# -------------------------
if not os.path.exists(OUTPUT_CSV):
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "attempt", "session_start_iso", "key_index", "key_char",
            "press_epoch_s", "release_epoch_s",
            "press_elapsed_ms", "release_elapsed_ms",
            "dwell_ms", "flight_ud_ms", "flight_dd_ms"
        ])

# -------------------------
# STATE
# -------------------------
attempt = 0
typed = ""
press_times = {}
events = []
start_perf = None
start_epoch = None
armed = not REQUIRE_ENTER_TO_START
session_buffer = []

# === WORKAROUND 1: MANUAL SHIFT TRACKING ===
shift_pressed = False
caps_lock_on = False
# ===========================================

# Queue for event processing (decouples hook from logic)
event_queue = Queue()
stop_flag = threading.Event()


# -------------------------
# HELPERS
# -------------------------
def printable_from_event_name(name: str):
    """Convert keyboard.event.name to printable character."""
    # === WORKAROUND 1: MODIFIED FUNCTION ===
    global shift_pressed, caps_lock_on
    
    if name == "space":
        return " "
    if len(name or "") == 1:
        # Handle capitalization based on manual shift/caps tracking
        if name.isalpha():
            if shift_pressed or caps_lock_on:
                return name.upper()
        return name
    return None
    # =======================================


def reset_attempt(msg=None):
    """Reset state for new attempt."""
    global typed, press_times, events, start_perf, start_epoch, armed
    # === WORKAROUND 1: RESET MODIFIER STATES ===
    global shift_pressed, caps_lock_on
    shift_pressed = False
    caps_lock_on = False
    # ===========================================
    typed = ""
    press_times.clear()
    events.clear()
    start_perf = None
    start_epoch = None
    if REQUIRE_ENTER_TO_START:
        armed = False
        print("\n— Attempt reset. Press ENTER to arm the next attempt. —")
    if msg:
        print(msg)


def arm_next_attempt():
    global armed
    armed = True
    print("Ready. Type the phrase:")


def attempt_is_complete_and_valid():
    return (typed == TARGET_PHRASE) and (len(events) >= len(TARGET_PHRASE))


def buffer_attempt(attempt_no):
    """Store completed attempt to memory buffer."""
    evts_copy = list(events)
    session_buffer.append((attempt_no, evts_copy, start_perf, start_epoch))
    print(f"[DEBUG] Buffered {len(evts_copy)} events for attempt {attempt_no}")


# -------------------------
# LOGIC (runs in worker thread)
# -------------------------
def handle_event(e: keyboard.KeyboardEvent):
    global start_perf, start_epoch, typed, attempt, armed
    # === WORKAROUND 1: ACCESS MODIFIER STATES ===
    global shift_pressed, caps_lock_on
    # ============================================

    ch = printable_from_event_name(e.name)
    now_perf = time.perf_counter()
    now_epoch = getattr(e, "time", time.time())

    # === WORKAROUND 1: MANUAL MODIFIER TRACKING ===
    # Track Shift key state
    if e.name == 'shift':
        if e.event_type == 'down':
            shift_pressed = True
        else:  # key up
            shift_pressed = False
        return  # Don't process shift as regular key
    
    # Track Caps Lock key state (toggles on press)
    if e.name == 'caps lock' and e.event_type == 'down':
        caps_lock_on = not caps_lock_on
        return  # Don't process caps lock as regular key
    # ==============================================

    # ---------- ARM ----------
    if REQUIRE_ENTER_TO_START and e.event_type == 'down' and e.name == 'enter' and not armed:
        arm_next_attempt()
        return

    if not armed:
        return

    # ---------- CONTROL KEYS ----------
    if e.event_type == 'down' and e.name == 'backspace':
        reset_attempt("Backspace pressed — restarting attempt.")
        return
    if e.event_type == 'down' and e.name == 'esc':
        print("ESC pressed — exiting.")
        stop_flag.set()
        return

    # ---------- KEY DOWN ----------
    if e.event_type == 'down' and ch is not None:
        if start_perf is None:
            start_perf = now_perf
            start_epoch = now_epoch
        token = (ch, len(events))  # order key
        press_times[token] = (now_perf, now_epoch)

        candidate = typed + ch
        if not TARGET_PHRASE.startswith(candidate):
            reset_attempt("Mistyped — attempt reset.")
            return
        typed = candidate

    # ---------- KEY UP ----------
    elif e.event_type == 'up' and ch is not None:
        # find matching press
        match_token = None
        for token in sorted(press_times.keys(), key=lambda t: t[1], reverse=True):
            if token[0] == ch:
                match_token = token
                break
        if match_token is None:
            return

        p_perf, p_epoch = press_times.pop(match_token, (None, None))
        events.append((ch, p_perf, now_perf, p_epoch, now_epoch))

        # check for completion (non-blocking)
        if len(typed) == len(TARGET_PHRASE):
            threading.Timer(0.1, finalize_attempt).start()


def finalize_attempt():
    """Check and buffer attempt after all releases are likely captured."""
    global attempt
    if attempt_is_complete_and_valid():
        attempt += 1
        buffer_attempt(attempt)
        print(f"✅ Attempt {attempt}/{NUM_ATTEMPTS} recorded (buffered).")
    else:
        print(f"⚠️ Attempt discarded ({len(events)}/{len(TARGET_PHRASE)} events). Try again.")
    reset_attempt()
    if attempt >= NUM_ATTEMPTS:
        stop_flag.set()


def event_processor():
    """Thread target: consume events from queue."""
    while not stop_flag.is_set():
        try:
            e = event_queue.get(timeout=0.1)
        except:
            continue
        handle_event(e)
    print("Event processor exiting...")


def on_key_event(e):
    """Very lightweight hook callback."""
    event_queue.put(e)


# -------------------------
# ENTRY POINT
# -------------------------
if __name__ == "__main__":
    print("Typing Logger (keyboard, threaded buffered version)")
    print(f"Target phrase: {TARGET_PHRASE}")
    print(f"Goal: {NUM_ATTEMPTS} clean attempts.")
    if REQUIRE_ENTER_TO_START:
        print("- Press ENTER to arm each attempt.\n")
    
    # === WORKAROUND 1: INITIAL MODIFIER STATE ===
    print(f"[DEBUG] Initial state - Shift: {shift_pressed}, Caps Lock: {caps_lock_on}")
    # ============================================

    worker = threading.Thread(target=event_processor, daemon=True)
    worker.start()

    keyboard.unhook_all()
    keyboard.hook(on_key_event)

    try:
        while not stop_flag.is_set():
            time.sleep(0.1)
    finally:
        keyboard.unhook_all()
        event_queue.put(None)
        worker.join(timeout=1.0)

        # ---------- WRITE BUFFER TO CSV ----------
        with open(OUTPUT_CSV, "a", newline="") as f:
            w = csv.writer(f)
            for attempt_no, evts, start_perf_, start_epoch_ in session_buffer:
                evts = sorted(evts, key=lambda e: e[1])
                for i, (ch, p_perf, r_perf, p_epoch, r_epoch) in enumerate(evts):
                    press_elapsed_ms   = (p_perf - start_perf_) * 1000.0
                    release_elapsed_ms = (r_perf - start_perf_) * 1000.0
                    dwell_ms           = (r_perf - p_perf) * 1000.0
                    if i == 0:
                        flight_ud_ms = flight_dd_ms = 0.0
                    else:
                        prev = evts[i-1]
                        flight_ud_ms = (p_perf - prev[2]) * 1000.0
                        flight_dd_ms = (p_perf - prev[1]) * 1000.0
                    w.writerow([
                        attempt_no,
                        datetime.fromtimestamp(start_epoch_).isoformat(timespec="seconds"),
                        i+1, ch,
                        f"{p_epoch:.6f}", f"{r_epoch:.6f}",
                        f"{press_elapsed_ms:.3f}", f"{release_elapsed_ms:.3f}",
                        f"{dwell_ms:.3f}", f"{flight_ud_ms:.3f}", f"{flight_dd_ms:.3f}"
                    ])
        print(f"\n✅ All buffered data ({len(session_buffer)} attempts) written to '{OUTPUT_CSV}'.")