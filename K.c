// Keystroke Logger (C) — clean CSV, real timestamps, modifiers kept
// ---------------------------------------------------------------
// gcc Keydown.c -o logger.exe -luser32
// cl Keydown.c /Fe:logger.exe user32.lib /D_CRT_SECURE_NO_WARNINGS

#include <windows.h>
#include <stdio.h>
#include <time.h>
#include <string.h>
#include <direct.h>

#define TARGET_PHRASE "vpwjkeurkb"
#define NUM_ATTEMPTS  5
#define REQUIRE_ENTER_TO_START 1

#define MAX_EVENTS    512
#define MAX_ATTEMPTS  10
#define MAX_NAME_LEN  64

#define CLAMP0(x) ((x) < 0.0 ? 0.0 : (x))

typedef struct {
    int   vk;
    char  ch;               // printable, 0 if not
    char  keyname[16];      // e.g. SHIFT_L
    double press_ms;        // global ms from qpc0
    double release_ms;      // global ms from qpc0
} KeyEvent;

typedef struct {
    int attempt_no;
    int count;
    KeyEvent events[MAX_EVENTS];
    double start_ms;        // global ms at attempt start
    time_t start_epoch;     // wall clock at attempt start
} AttemptBuffer;

static AttemptBuffer attempts[MAX_ATTEMPTS];
static AttemptBuffer cur;          // current attempt
static int cur_started = 0;        // <<< important: marks start of attempt

static int attempt_index = 0;
static int armed = !REQUIRE_ENTER_TO_START;
static int running = 1;

static char typed[256] = {0};

static double g_freq = 0.0;
static LARGE_INTEGER g_qpc0;
static int gShiftDown = 0;

static char g_user_name[MAX_NAME_LEN] = "student";
static char g_output_csv[256] = "student_keystrokes.csv";

// -------------------------------------------------
double now_ms(void) {
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (double)(c.QuadPart - g_qpc0.QuadPart) * 1000.0 / g_freq;
}

void vk_to_name(int vk, char *out, size_t n) {
    switch (vk) {
    case VK_LSHIFT:  strncpy(out, "SHIFT_L", n); break;
    case VK_RSHIFT:  strncpy(out, "SHIFT_R", n); break;
    case VK_SHIFT:   strncpy(out, "SHIFT", n); break;
    case VK_CAPITAL: strncpy(out, "CAPS", n); break;
    case VK_RETURN:  strncpy(out, "ENTER", n); break;
    case VK_BACK:    strncpy(out, "BACKSPACE", n); break;
    case VK_ESCAPE:  strncpy(out, "ESC", n); break;
    default: _snprintf_s(out, n, _TRUNCATE, "VK_%02X", vk); break;
    }
}

char translate_vk_to_char(DWORD vk, int shiftDown) {
    SHORT caps = GetKeyState(VK_CAPITAL);
    int capsOn = (caps & 0x0001) != 0;

    if (vk >= 'A' && vk <= 'Z') {
        int upper = (shiftDown ? 1 : 0) ^ (capsOn ? 1 : 0);
        return upper ? (char)vk : (char)(vk + 32);
    }

    if (vk >= '0' && vk <= '9') {
        if (!shiftDown) return (char)vk;
        switch (vk) {
        case '1': return '!';
        case '2': return '@';
        case '3': return '#';
        case '4': return '$';
        case '5': return '%';
        case '6': return '^';
        case '7': return '&';
        case '8': return '*';
        case '9': return '(';
        case '0': return ')';
        }
    }

    if (vk == VK_SPACE) return ' ';

    return 0;
}

int is_printable_for_phrase(char c) {
    return (c >= 32 && c <= 126);
}

void reset_attempt(const char *msg) {
    cur.count = 0;
    cur_started = 0;
    typed[0] = '\0';
    if (REQUIRE_ENTER_TO_START)
        armed = 0;
    if (msg) printf("%s\n", msg);
    if (REQUIRE_ENTER_TO_START)
        printf("PRESS ENTER to arm every attempt. \n");
}

void arm_next_attempt(void) {
    armed = 1;
    printf("Ready. Type the phrase: %s\n", TARGET_PHRASE);
}

int attempt_is_complete(void) {
    return strcmp(typed, TARGET_PHRASE) == 0;
}

void buffer_attempt(void) {
    if (attempt_index >= NUM_ATTEMPTS) return;
    attempts[attempt_index] = cur;
    attempts[attempt_index].attempt_no = attempt_index + 1;
    attempt_index++;
    printf(" CORRECT Attempt :) ;) %d/%d recorded.\n", attempt_index, NUM_ATTEMPTS);
}

// -------------------------------------------------
// CSV writer
void write_csv(void) {
    int need_header = 0;
    FILE *test = fopen(g_output_csv, "r");
    if (!test) need_header = 1;
    else fclose(test);

    FILE *f = fopen(g_output_csv, "a");
    if (!f) {
        printf("⚠️ could not open %s\n", g_output_csv);
        return;
    }

    if (need_header) {
        fprintf(f,
            "user,attempt_id,attempt_time,event_idx,vk,key,ch,"
            "press_ms,release_ms,press_rel_ms,release_rel_ms,"
            "dwell_ms,flight_ud_ms,flight_dd_ms\n");
    }

    char timebuf[64];

    for (int a = 0; a < attempt_index; a++) {
        AttemptBuffer *buf = &attempts[a];

        struct tm *tm_info = localtime(&buf->start_epoch);
        if (tm_info)
            strftime(timebuf, sizeof(timebuf), "%Y-%m-%d %H:%M:%S", tm_info);
        else
            strcpy(timebuf, "1970-01-01 00:00:00");

        for (int i = 0; i < buf->count; i++) {
            KeyEvent *e = &buf->events[i];

            // ignore completely empty rows (safety)
            if (e->vk == 0 && e->press_ms == 0.0 && e->release_ms == 0.0)
                continue;

            double press_rel   = e->press_ms   - buf->start_ms;
            double release_rel = e->release_ms - buf->start_ms;

            press_rel   = CLAMP0(press_rel);
            release_rel = CLAMP0(release_rel);

            double dwell = e->release_ms - e->press_ms;
            dwell = CLAMP0(dwell);

            double flight_ud = 0.0;
            double flight_dd = 0.0;
            if (i > 0) {
                KeyEvent *prev = &buf->events[i-1];
                flight_ud = e->press_ms - prev->release_ms;
                flight_dd = e->press_ms - prev->press_ms;
                flight_ud = CLAMP0(flight_ud);
                flight_dd = CLAMP0(flight_dd);
            }

            if (e->ch != 0) {
                fprintf(f,
                    "%s,%d,%s,%d,%d,-,%c,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\n",
                    g_user_name,
                    buf->attempt_no,
                    timebuf,
                    i+1,
                    e->vk,
                    e->ch,
                    e->press_ms,
                    e->release_ms,
                    press_rel,
                    release_rel,
                    dwell,
                    flight_ud,
                    flight_dd
                );
            } else {
                fprintf(f,
                    "%s,%d,%s,%d,%d,%s,-,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\n",
                    g_user_name,
                    buf->attempt_no,
                    timebuf,
                    i+1,
                    e->vk,
                    e->keyname,
                    e->press_ms,
                    e->release_ms,
                    press_rel,
                    release_rel,
                    dwell,
                    flight_ud,
                    flight_dd
                );
            }
        }
    }

    fclose(f);

    char cwd[512];
    if (_getcwd(cwd, sizeof(cwd))) {
        printf("\n✅ Data written to %s\\%s\n", cwd, g_output_csv);
    } else {
        printf("\n✅ Data written to %s\n", g_output_csv);
    }
}

// -------------------------------------------------
LRESULT CALLBACK KeyboardProc(int code, WPARAM wParam, LPARAM lParam) {
    if (code < 0)
        return CallNextHookEx(NULL, code, wParam, lParam);

    KBDLLHOOKSTRUCT *p = (KBDLLHOOKSTRUCT *)lParam;
    DWORD vk = p->vkCode;
    int is_up   = (wParam == WM_KEYUP || wParam == WM_SYSKEYUP);
    int is_down = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);

    // ESC → quit
    if (vk == VK_ESCAPE && is_down) {
        running = 0;
        PostQuitMessage(0);
        return 1;
    }

    // update shift state
    if (vk == VK_SHIFT || vk == VK_LSHIFT || vk == VK_RSHIFT) {
        if (is_down) gShiftDown = 1;
        else if (is_up) gShiftDown = 0;
    }

    // ENTER to arm
    if (REQUIRE_ENTER_TO_START && vk == VK_RETURN && is_down && !armed) {
        arm_next_attempt();
        return 1;
    }

    if (!armed) {
        return CallNextHookEx(NULL, code, wParam, lParam);
    }

    // BACKSPACE resets
    if (vk == VK_BACK && is_down) {
        reset_attempt("Backspace pressed — restarting attempt.");
        return 1;
    }

    // ------------- KEYDOWN -------------
    if (is_down) {
        // first key of attempt
        if (!cur_started) {
            cur.start_ms    = now_ms();
            cur.start_epoch = time(NULL);
            cur_started     = 1;
        }

        char ch = translate_vk_to_char(vk, gShiftDown);

        // phrase logic: only printable affects typed[]
        if (ch && is_printable_for_phrase(ch)) {
            size_t len = strlen(typed);
            typed[len] = ch;
            typed[len+1] = '\0';

            if (strncmp(TARGET_PHRASE, typed, strlen(typed)) != 0) {
                reset_attempt("Mistyped :( Press ENTER to Arm)");
                return 1;
            }
        }

        if (cur.count < MAX_EVENTS) {
            KeyEvent *e = &cur.events[cur.count];
            e->vk = (int)vk;
            e->ch = ch;
            e->press_ms = now_ms();
            e->release_ms = e->press_ms;   // init to press, will overwrite on real keyup
            vk_to_name((int)vk, e->keyname, sizeof(e->keyname));
            cur.count++;                   // <<< increment ON keydown
        }
    }
    // ------------- KEYUP -------------
    else if (is_up) {
        // find last event with same vk
        for (int i = cur.count - 1; i >= 0; i--) {
            KeyEvent *e = &cur.events[i];
            if (e->vk == (int)vk) {
                double rel = now_ms();
                if (rel < e->press_ms) rel = e->press_ms;
                e->release_ms = rel;
                break;
            }
        }

        // check phrase completion
        if (strlen(typed) == strlen(TARGET_PHRASE)) {
            if (attempt_is_complete()) {
                buffer_attempt();
                if (attempt_index >= NUM_ATTEMPTS) {
                    running = 0;
                    PostQuitMessage(0);
                }
            } else {
                printf("⚠️ Attempt discarded.\n");
            }
            reset_attempt(NULL);
        }
    }

    return CallNextHookEx(NULL, code, wParam, lParam);
}

// -------------------------------------------------
void get_user_name_and_filename(void) {
    char name[MAX_NAME_LEN] = {0};

    printf("Enter your full name (no spaces): ");
    fflush(stdout);

    if (fgets(name, sizeof(name), stdin)) {
        size_t len = strlen(name);
        if (len && (name[len-1] == '\n' || name[len-1] == '\r'))
            name[len-1] = '\0';

        for (size_t i = 0; i < strlen(name); i++) {
            char c = name[i];
            if (c == '\\' || c == '/' || c == ':' || c == '*' ||
                c == '?'  || c == '"' || c == '<' || c == '>' || c == '|') {
                name[i] = '_';
            }
        }

        if (strlen(name) == 0) {
            strcpy(g_user_name, "student");
            strcpy(g_output_csv, "student_keystrokes.csv");
        } else {
            strncpy(g_user_name, name, sizeof(g_user_name));
            _snprintf_s(g_output_csv, sizeof(g_output_csv), _TRUNCATE,
                        "%s_keystrokes.csv", name);
        }
    } else {
        strcpy(g_user_name, "student");
        strcpy(g_output_csv, "student_keystrokes.csv");
    }

    printf("Data will be saved to: %s\n\n", g_output_csv);
}

// -------------------------------------------------
int main(void) {
    printf("=================================================\n");
    printf(" Keystroke Logger (clean CSV)\n");
    printf(" Target phrase: %s\n", TARGET_PHRASE);
    printf(" Attempts: %d\n", NUM_ATTEMPTS);
    printf(" ESC = quit\n");
    printf("=================================================\n");

    get_user_name_and_filename();

    if (REQUIRE_ENTER_TO_START)
        printf("- Press ENTER to arm each attempt. , if you mistype you will be notified, press ENTER to re-arm after mistyping.\n");

    LARGE_INTEGER li;
    QueryPerformanceFrequency(&li);
    g_freq = (double)li.QuadPart;
    QueryPerformanceCounter(&g_qpc0);

    HHOOK hook = SetWindowsHookEx(WH_KEYBOARD_LL, KeyboardProc, NULL, 0);
    if (!hook) {
        printf("Failed to install hook.\n");
        return 1;
    }

    MSG msg;
    while (running && GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    UnhookWindowsHookEx(hook);
    write_csv();
    return 0;
}
