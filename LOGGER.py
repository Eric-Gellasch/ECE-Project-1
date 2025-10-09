import time
import csv
import os
from datetime import datetime
from pynput.keyboard import Key, Listener

print("Typing Logger v3.2 — REQUIRE_ENTER_TO_START = True")  # banner to confirm correct script

# =========================
# CONFIG
# =========================
TARGET_PHRASE = "Football123$"
NUM_ATTEMPTS = 5
OUTPUT_CSV = "typing_cadence_full_v3.csv"

# Require ENTER before each attempt to avoid “first key dropped” race.
REQUIRE_ENTER_TO_START = True

# =========================
# OUTPUT HEADER (idempotent)
# =========================
if not os.path.exists(OUTPUT_CSV):
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "attempt","session_start_iso","key_index","key_char",
            "press_epoch_s","release_epoch_s","press_elapsed_ms","release_elapsed_ms",
            "dwell_ms","flight_ud_ms","flight_dd_ms"
        ])

# =========================
# STATE (per session)
# =========================
attempt = 0                      # attempt counter
typed = ""                       # running typed chars (validated against TARGET_PHRASE prefix)
press_times = {}                 # (char, seq) -> (press_perf, press_epoch)
events = []                      # (char, press_perf, release_perf, press_epoch, release_epoch)
start_perf = None                # perf_counter at attempt start (monotonic, high-res)
start_epoch = None               # wall clock at attempt start (for human-readable timestamp)
seq = 0                          # increasing id to pair press/release robustly
armed = not REQUIRE_ENTER_TO_START  # True when ready to accept a new attempt

def reset_attempt(msg=None):
    """
    Reset per-attempt state, keep session running.
    If ENTER is required, disarm so user must re-arm next attempt.
    """
    global typed, press_times, events, start_perf, start_epoch, armed
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
    """Allow the next attempt to start."""
    global armed
    armed = True
    print("Ready. Type the phrase:")

def attempt_is_complete_and_valid():
    """
    Accept an attempt only if:
      1) typed string equals TARGET_PHRASE, and
      2) captured events count equals phrase length (no dropped keys).
    """
    return (typed == TARGET_PHRASE) and (len(events) == len(TARGET_PHRASE))

def save_attempt(attempt_no):
    """
    Write one row per key with:
      - dwell_ms: (release - press)
      - flight_ud_ms: press_n - release_{n-1}  (may be negative if overlapping)
      - flight_dd_ms: press_n - press_{n-1}    (non-negative; usually your primary inter-key metric)
      - *_elapsed_ms: elapsed from attempt start (nice for plotting)
    """
    evts = sorted(events, key=lambda e: e[1])  # order by press_perf

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
                flight_ud_ms = (p_perf - prev[2]) * 1000.0  # current press - previous release
                flight_dd_ms = (p_perf - prev[1]) * 1000.0  # current press - previous press

            w.writerow([
                attempt_no,
                datetime.fromtimestamp(start_epoch).isoformat(timespec="seconds"),
                i+1, ch,
                f"{p_epoch:.6f}", f"{r_epoch:.6f}",
                f"{press_elapsed_ms:.3f}", f"{release_elapsed_ms:.3f}",
                f"{dwell_ms:.3f}", f"{flight_ud_ms:.3f}", f"{flight_dd_ms:.3f}"
            ])
    print(f"[DEBUG] saved {len(events)} rows, typed='{typed}' at {datetime.fromtimestamp(start_epoch).isoformat(timespec='seconds')}")

def printable_char_from_key(key):
    """Return a printable single-character string, or None for non-printables."""
    if hasattr(key, "char") and key.char is not None:
        return key.char
    if key == Key.space:
        return " "
    return None

def on_press(key):
    global start_perf, start_epoch, typed, seq, armed

    # ENTER arms the next attempt (if enabled)
    if REQUIRE_ENTER_TO_START and key == Key.enter and not armed:
        arm_next_attempt()
        return

    if not armed:
        return

    now_perf = time.perf_counter()
    now_epoch = time.time()

    # Stamp attempt start times on the first printable key
    if start_perf is None:
        start_perf = now_perf
        start_epoch = now_epoch

    ch = printable_char_from_key(key)
    if ch is None:
        # Ignore modifiers; special handling for backspace/ESC
        if key == Key.backspace:
            reset_attempt("Backspace pressed — restarting attempt.")
        elif key == Key.esc:
            print("ESC pressed — exiting.")
            return False
        return

    # Record key-down with unique token for robust matching
    seq += 1
    token = (ch, seq)
    press_times[token] = (now_perf, now_epoch)

    # Validate prefix vs target; reset immediately on deviation
    candidate = typed + ch
    if not TARGET_PHRASE.startswith(candidate):
        reset_attempt("Mistyped — attempt reset.")
        return
    typed = candidate

def on_release(key):
    """Pair releases with their presses, record event, and save complete attempts."""
    global attempt
    if not armed:
        return

    ch = printable_char_from_key(key)
    if ch is None:
        return

    now_perf = time.perf_counter()
    now_epoch = time.time()

    # Find latest pending press for this char (newest-first search)
    match_token = None
    for token in sorted(press_times.keys(), key=lambda t: t[1], reverse=True):
        if token[0] == ch:
            match_token = token
            break
    if match_token is None:
        # Rare driver quirk; ignore quietly
        return

    p_perf, p_epoch = press_times.pop(match_token)
    events.append((ch, p_perf, now_perf, p_epoch, now_epoch))

    # If we’ve typed the full length, verify and either save or discard
    if len(typed) == len(TARGET_PHRASE):
        if attempt_is_complete_and_valid():
            attempt += 1
            save_attempt(attempt)
            print(f"✅ Attempt {attempt}/{NUM_ATTEMPTS} recorded.")
        else:
            print("⚠️ Attempt discarded (mismatch between typed string and captured events). Try again.")
        reset_attempt()
        if attempt >= NUM_ATTEMPTS:
            print(f"\nAll {NUM_ATTEMPTS} successful attempts complete.")
            return False

# =========================
# PROMPT
# =========================
print("\nType the phrase exactly:\n")
print(f"👉  {TARGET_PHRASE}\n")
print(f"Goal: {NUM_ATTEMPTS} clean, correct attempts.")
print("- Backspace resets the current attempt.")
print("- ESC quits.")
print("- Press ENTER to arm each attempt (prevents first-key drop).\n")

with Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

print(f"\nTyping cadence data saved to '{OUTPUT_CSV}'.")