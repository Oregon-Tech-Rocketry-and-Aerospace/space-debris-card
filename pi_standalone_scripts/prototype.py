import cv2
import numpy as np
import datetime
import threading
import queue

def make_1080p(video):
  video.set(3, 1920)
  video.set(4, 1080)

def make_720p(video):
  video.set(3, 1280)
  video.set(4, 720)

def make_480p(video):
   video.set(3, 640)
   video.set(4, 480)

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
  # Create a VideoCapture object
  cap = cv2.VideoCapture(0)
  
  # Check if camera opened successfully
  if (cap.isOpened() == False):
    print("Unable to read camera feed")
  
  # Change default resolution of the system.
  make_480p(cap)

  # Default resolutions of the frame are obtained.The default resolutions are system dependent.
  # We convert the resolutions from float to integer.
  frame_width = int(cap.get(3))
  frame_height = int(cap.get(4))
  fps = cap.get(cv2.CAP_PROP_FPS)
  cap.set(cv2.CAP_PROP_FPS, 90)
  print("Framerate = %0.2f FPS" % (fps))

  # Get current datetime and compose output video file name.
  dt = datetime.datetime.now()
  output_file = f"{dt.year}-{dt.month}-{dt.day}_{dt.hour}:{dt.minute}:{dt.second}.avi"
  
  # Define the codec and create VideoWriter object.The output is stored in 'outpy.avi' file.
  out = cv2.VideoWriter(output_file,cv2.VideoWriter_fourcc('M','J','P','G'), 30, (frame_width,frame_height))

  # Keyboard input queue to pass data from the thread reading the keyboard inputs to the main thread.
  inputQueue = queue.Queue()

  # Create & start a thread to read keyboard inputs.
  # Set daemon to True to auto-kill this thread when all other non-daemonic threads are exited. This is desired since
  # this thread has no cleanup to do, which would otherwise require a more graceful approach to clean up then exit.
  inputThread = threading.Thread(target=read_kbd_input, args=(inputQueue,), daemon=True)
  inputThread.start()

  terminated = False # Sets initial condition on while loop

  frame_count = 0

  while not terminated:
    # wait before each frame is written. wait is relative to fps
    cv2.waitKey(int(1000 / fps))
    frame_count = frame_count + 1

    ret, frame = cap.read()
  
    if ret == True: 
      
      # Write the frame into the file
      out.write(frame)
  
    # Break the loop
    else:
      terminated = True

    # if the keyboard input has been entered, check input
    if inputQueue.qsize() > 0:
      input_str = inputQueue.get()

      # If user entered a q, quit the program
      if input_str == "q":
        terminated = True
  
  # When everything done, release the video capture and video write objects
  cap.release()
  out.release()
  
  print(frame_count)
  print(1000 / fps)

if __name__ == "__main__":
  main()
