import time
import csv
import os
from datetime import datetime
from pynput.keyboard import Key, Listener

# ---------- CONFIG ----------
TARGET_PHRASE = "Football123$"
NUM_ATTEMPTS = 5
OUTPUT_CSV = "typing_cadence_full.csv"

# ---------- INITIALIZE OUTPUT ----------
if not os.path.exists(OUTPUT_CSV):
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "attempt", "session_start_iso", "key_index",
            "key_char", "press_time", "release_time",
            "dwell_time", "flight_time"
        ])

# ---------- STATE VARIABLES ----------
attempt = 0
typed = ""
press_times = {}
events = []
start_time = None
mistake = False

def reset_attempt(msg=None):
    """Clear temporary data for new attempt."""
    global typed, press_times, events, start_time, mistake
    typed = ""
    press_times.clear()
    events.clear()
    start_time = None
    mistake = False
    if msg:
        print(msg)

def save_attempt(attempt_no, start_ts, evts):
    """
    Write one row per key with correct dwell and flight times.
    Each attempt is isolated from the previous one.
    """
    # Sort events by press time just in case of async ordering
    evts = sorted(evts, key=lambda e: e[1])

    with open(OUTPUT_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        for i, (ch, press, release) in enumerate(evts):
            dwell = release - press
            if i == 0:
                flight = 0.0  # no previous key in this attempt
            else:
                flight = press - evts[i - 1][2]  # release of prev to press of curr

            writer.writerow([
                attempt_no,
                datetime.fromtimestamp(start_ts).isoformat(),
                i + 1, ch,
                f"{press:.6f}", f"{release:.6f}",
                f"{dwell:.6f}", f"{flight:.6f}"
            ])

def on_press(key):
    global start_time, typed, mistake

    if start_time is None:
        start_time = time.time()

    # Determine printable character
    char = None
    if hasattr(key, "char") and key.char is not None:
        char = key.char
    elif key == Key.space:
        char = " "
    elif key == Key.backspace:
        reset_attempt("Backspace pressed — restarting attempt.")
        return
    elif key == Key.esc:
        print("ESC pressed, exiting.")
        return False

    press_times[id(key)] = time.time()

    if char is not None and not mistake:
        typed += char
        # Check accuracy so far
        if not TARGET_PHRASE.startswith(typed):
            reset_attempt("Mistyped — attempt reset.")
            mistake = True

def on_release(key):
    global attempt, typed

    pid = id(key)
    if pid in press_times:
        p_time = press_times.pop(pid)
        r_time = time.time()
        char = None
        if hasattr(key, "char") and key.char is not None:
            char = key.char
        elif key == Key.space:
            char = " "
        if char:
            events.append((char, p_time, r_time))

    # When phrase fully typed and correct
    if len(typed) == len(TARGET_PHRASE) and not mistake:
        attempt += 1
        save_attempt(attempt, start_time, events)
        print(f"✅ Attempt {attempt}/{NUM_ATTEMPTS} recorded.")
        reset_attempt()
        if attempt >= NUM_ATTEMPTS:
            print(f"\nAll {NUM_ATTEMPTS} successful attempts complete.")
            return False
        

# ---------- USER PROMPT ----------
print(f"\nType the phrase exactly as shown below:\n")
print(f"👉  {TARGET_PHRASE}\n")
print(f"You must type it correctly {NUM_ATTEMPTS} times in total.")
print("If you make a mistake or press Backspace, you'll need to restart that attempt.")
print("Press ESC at any time to exit.\n")
print("Ready when you are — start typing now...\n")
with Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()


print(f"Typing cadence data saved to '{OUTPUT_CSV}'. Goodbye!")