import picamera
import cv2
import numpy as np
import datetime
import threading
import queue

def read_kbd_input(inputQueue):
  print('Press q to quit:')
  while (True):
      # Receive keyboard input from user.
      input_str = input()

      # Enqueue this input string.
      # Note: Lock not required here since we are only calling a single Queue method, not a sequence of them 
      # which would otherwise need to be treated as one atomic operation.
      inputQueue.put(input_str)
 
def main():
  camera = picamera.PiCamera()
  # Optional resolutions: 1920x1080, 1280x720, 640x480
  camera.resolution = (1280, 720)

  # Get current datetime and compose output video file name.
  dt = datetime.datetime.now()
  output_file = f"{dt.year}-{dt.month}-{dt.day}_{dt.hour}h{dt.minute}m{dt.second}s.h264"

  # Keyboard input queue to pass data from the thread reading the keyboard inputs to the main thread.
  inputQueue = queue.Queue()

  # Create & start a thread to read keyboard inputs.
  # Set daemon to True to auto-kill this thread when all other non-daemonic threads are exited. This is desired since
  # this thread has no cleanup to do, which would otherwise require a more graceful approach to clean up then exit.
  inputThread = threading.Thread(target=read_kbd_input, args=(inputQueue,), daemon=True)
  inputThread.start()

  camera.start_recording(output_file)

  terminated = False # Sets initial condition on while loop

  while not terminated:
    # if the keyboard input has been entered, check input
    if inputQueue.qsize() > 0:
      input_str = inputQueue.get()

      # If user entered a q, quit the program
      if input_str == "q":
        terminated = True

  camera.stop_recording()
  print("Finished recording")

if __name__ == "__main__":
  main()