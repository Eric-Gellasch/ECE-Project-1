"""
KEYLOGGER_keyboard.py
Keyboard-based typing cadence logger using the low-level `keyboard` library.
Keeps the same logic/strict validation as your previous pynput script.

Usage:
 - Install dependency: pip install keyboard
 - Run the script (Windows): open PowerShell/CMD "Run as Administrator", then: python KEYLOGGER_keyboard.py
 - Press ENTER to arm (if REQUIRE_ENTER_TO_START=True), then type the TARGET_PHRASE exactly.
 - Backspace resets an attempt. ESC exits.
"""

import time
import csv
import os
from datetime import datetime
import keyboard  # pip install keyboard

# -------------------------
# CONFIG
# -------------------------
TARGET_PHRASE = "Football123$"
NUM_ATTEMPTS = 5
OUTPUT_CSV = "KEY_Using_Keyboard.csv"

# If True, require ENTER to arm each attempt (prevents first-key drop)
REQUIRE_ENTER_TO_START = True

# -------------------------
# OUTPUT HEADER (idempotent)
# -------------------------
if not os.path.exists(OUTPUT_CSV):
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "attempt","session_start_iso","key_index","key_char",
            "press_epoch_s","release_epoch_s","press_elapsed_ms","release_elapsed_ms",
            "dwell_ms","flight_ud_ms","flight_dd_ms"
        ])

# -------------------------
# STATE
# -------------------------
attempt = 0
typed = ""                       # assembled visible chars (prefix-checked)
press_times = {}                 # maps token -> (press_perf, press_epoch)
events = []                      # list of (char, press_perf, release_perf, press_epoch, release_epoch)
start_perf = None
start_epoch = None
seq = 0                          # unique token id for press/release pairing
armed = not REQUIRE_ENTER_TO_START

# -------------------------
# HELPERS
# -------------------------
def printable_from_event_name(name: str):
    """
    Map keyboard.event.name to a printable char.
    The keyboard library usually returns printable characters directly,
    and returns names like 'space', 'enter', 'shift' for non-printables.
    We convert 'space' -> ' ' and leave printable names unchanged.
    """
    if name is None:
        return None
    if name == "space":
        return " "
    # keyboard sometimes returns multi-character names like 'left shift' - ignore those
    if len(name) == 1:
        return name
    # Some platforms may return characters like '$' directly (ok).
    # If name is longer than 1 and not 'space', treat as non-printable.
    return None

def reset_attempt(msg=None):
    """Clear per-attempt state; disarm if ENTER required."""
    global typed, press_times, events, start_perf, start_epoch, seq, armed
    typed = ""
    press_times.clear()
    events.clear()
    start_perf = None
    start_epoch = None
    # keep seq monotonic across attempts
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
    return (typed == TARGET_PHRASE) and (len(events) == len(TARGET_PHRASE))

def save_attempt(attempt_no):
    """Persist rows exactly like previous format (press/release epoch + elapsed + dwell + flights)."""
    evts = sorted(events, key=lambda e: e[1])  # sort by press_perf
    with open(OUTPUT_CSV, "a", newline="") as f:
        w = csv.writer(f)
        for i, (ch, p_perf, r_perf, p_epoch, r_epoch) in enumerate(evts):
            press_elapsed_ms   = (p_perf - start_perf) * 1000.0
            release_elapsed_ms = (r_perf - start_perf) * 1000.0
            dwell_ms           = (r_perf - p_perf) * 1000.0
            if i == 0:
                flight_ud_ms = 0.0
                flight_dd_ms = 0.0
            else:
                prev = evts[i-1]
                flight_ud_ms = (p_perf - prev[2]) * 1000.0
                flight_dd_ms = (p_perf - prev[1]) * 1000.0

            w.writerow([
                attempt_no,
                datetime.fromtimestamp(start_epoch).isoformat(timespec="seconds"),
                i+1, ch,
                f"{p_epoch:.6f}", f"{r_epoch:.6f}",
                f"{press_elapsed_ms:.3f}", f"{release_elapsed_ms:.3f}",
                f"{dwell_ms:.3f}", f"{flight_ud_ms:.3f}", f"{flight_dd_ms:.3f}"
            ])
    print(f"[DEBUG] saved {len(events)} rows, typed='{typed}' at {datetime.fromtimestamp(start_epoch).isoformat(timespec='seconds')}")

# -------------------------
# Event handlers using `keyboard` library
# -------------------------
def on_key_event(e: keyboard.KeyboardEvent):
    """
    This single-hook handler receives both 'down' and 'up' events.
    We will:
     - On 'down': record press time with a unique token (char, seq)
     - On 'up'  : find the most recent unmatched press token for that char and record the event
    """
    global start_perf, start_epoch, seq, typed, attempt, armed

    # IMPORTANT: keyboard event fields:
    #   e.event_type -> 'down' or 'up'
    #   e.name -> human-readable name (like 'a', 'space', '$', 'shift')
    #   e.time -> float seconds since epoch (same as time.time())
    # We will use time.perf_counter() for high-res elapsed timings.

    # Handle arming via ENTER (only on 'down' to avoid duplicate triggers)
    if REQUIRE_ENTER_TO_START and e.event_type == 'down' and e.name == 'enter' and not armed:
        arm_next_attempt()
        return

    # If not armed, ignore everything else
    if not armed:
        return

    # Map to printable char (None for modifiers)
    ch = printable_from_event_name(e.name)

    # Special keys handling while unarmed/armed:
    # Backspace resets immediately on 'down'
    if e.event_type == 'down' and e.name == 'backspace':
        reset_attempt("Backspace pressed — restarting attempt.")
        return

    # ESC to exit the entire program (on key-up to avoid double capture)
    if e.name == 'esc' and e.event_type == 'down':
        print("ESC pressed — exiting.")
        keyboard.unhook_all()
        return

    # If this is a printable key press
    now_perf = time.perf_counter()
    now_epoch = e.time if hasattr(e, "time") else time.time()

    if e.event_type == 'down' and ch is not None:
        # Stamp attempt start times on the first printable key
        if start_perf is None:
            start_perf = now_perf
            start_epoch = now_epoch

        # record press with unique token
        seq += 1
        token = (ch, seq)
        press_times[token] = (now_perf, now_epoch)

        # validate typed prefix (case sensitive)
        candidate = typed + ch
        if not TARGET_PHRASE.startswith(candidate):
            reset_attempt("Mistyped — attempt reset.")
            return
        typed = candidate

    # If this is a printable key release
    elif e.event_type == 'up' and ch is not None:
        # find most recent matching press token
        match_token = None
        # iterate newest-first
        for token in sorted(press_times.keys(), key=lambda t: t[1], reverse=True):
            if token[0] == ch:
                match_token = token
                break

        if match_token is None:
            # unmatched release - ignore quietly
            return

        p_perf, p_epoch = press_times.pop(match_token)
        events.append((ch, p_perf, now_perf, p_epoch, now_epoch))

        # If we've reached the length of the target, evaluate attempt
        if len(typed) == len(TARGET_PHRASE):
            if attempt_is_complete_and_valid():
                attempt += 1
                try:
                    save_attempt(attempt)
                    print(f"✅ Attempt {attempt}/{NUM_ATTEMPTS} recorded.")
                except PermissionError:
                    print("⚠️ PermissionError: could not write CSV. Close file if open (e.g., Excel) or run as admin.")
            else:
                print("⚠️ Attempt discarded (mismatch between typed string and captured events). Try again.")
            reset_attempt()
            if attempt >= NUM_ATTEMPTS:
                print(f"\nAll {NUM_ATTEMPTS} successful attempts complete.")
                keyboard.unhook_all()
                return

# -------------------------
# Program entrypoint
# -------------------------
if __name__ == "__main__":
    print("Typing Logger (keyboard) — REQUIRE_ENTER_TO_START =", REQUIRE_ENTER_TO_START)
    print("\nType the phrase exactly:\n")
    print(f"👉  {TARGET_PHRASE}\n")
    print(f"Goal: {NUM_ATTEMPTS} clean, correct attempts.")
    print("- Backspace resets the current attempt.")
    print("- ESC quits.")
    if REQUIRE_ENTER_TO_START:
        print("- Press ENTER to arm each attempt (prevents first-key drop).\n")
    else:
        print()

    # Hook all keyboard events to our handler
    keyboard.hook(on_key_event)

    # Block here until the hook is removed (i.e., ESC or attempts done)
    keyboard.wait()  # waits until all hooks are removed or program exit
    print(f"\nTyping cadence data saved to '{OUTPUT_CSV}'.")
