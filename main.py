import signal
import sys
import time
import RPi.GPIO as GPIO
import subprocess
import threading
from datetime import datetime, timedelta

# Setup GPIO pin for interrupts
BUTTON_GPIO = 16

# Recordings
# intro.wav - Regular intro
# evening.wav - Intro after 7pm
# caller_fifty.wav - Intro for 50th caller
# beep.wav - beep

# Finite State Machine for Phone
# FSM states are:
#   waiting - before any action
#   playing - playing pre-recorded message
#   recording - recording message via microphone

# FSM Transitions are:
#   waiting -> #play -> playing - GPIO interrupt, phone_down = False
#   playing -> #stopPlayback ->  waiting - GPIO interrupt, phone_down = True
#   playing -> #record -> recording - Playback ended, phone_down = False
#   recording -> #stopRecording -> waiting - GPIO interrupt, phone_down = True
#   recording -> #phoneStuck -> phone-stuck - Hit max recording duration
#   phone-stuck -> #wait -> waiting - GPIO interrupt, phone_down = True

class FSM:
  def __init__(self, usb_directory):
    self.state = 'waiting'
    self.transitions = {
      ('waiting', False): self.play,
      ('playing', True): self.stopPlayback,
      ('playing', False): self.record,
      ('recording', True): self.stopRecording,
      ('phone-stuck', True): self.wait,
      ('phone-stuck', False): self.phoneStuck
    }
    self.p = None
    self.r = None
    self.beep = None
    self.message_count = 0
    self.boot_up_time = datetime.now()
    self.recording_ended = False
    self.usb_directory = usb_directory

  def handleGPIOEvent(self, phone_down):
    if (self.state, phone_down) in self.transitions:
      self.transitions[(self.state, phone_down)]()

  def selectMessage(self):
    # First caller is message_count == 0
    if self.message_count == 49:
      return "caller_fifty.wav"
    if datetime.now() > (self.boot_up_time + timedelta(hours=8)):
      return "evening.wav"
    return "intro.wav"

  def play(self):
    print("Playing!")
    self.state = 'playing'
    # Start pre-recorded message via command
    def start_via_thread():
      time.sleep(0.25)
      message_file = self.selectMessage()
      self.p = subprocess.Popen(['aplay', message_file])
      returncode = self.p.wait()
      if returncode == 0:
        # Playback finished completely
        self.playBeep()
        if not GPIO.input(BUTTON_GPIO):
          self.record()
        else:
          self.wait()
      else:
        # Playback cancelled
        self.wait()

    threading.Thread(target=start_via_thread).start()

  def stopPlayback(self):
    if self.p:
      self.p.kill()
      self.p = None

  def wait(self):
    print("Waiting!")
    self.state = 'waiting'
    self.stopRecording()
    self.stopPlayback()

  def record(self):
    print("Recording!")
    self.state = 'recording'
    filename = "recordings/" + datetime.now().strftime("%d-%b-%Y_%H-%M-%S") + "_recording.wav"
    backup_spot = self.usb_directory + "/" + filename
    # Start recording via command
    def start_via_thread():
      self.r = subprocess.Popen(['arecord', '--device=hw:1,0', '--format', 'S16_LE', '-d', '180', '--rate', '44100', '-c1', filename])
      self.r.wait()
      subprocess.run(['cp', filename, backup_spot])
      if self.recording_ended:
        # Put down the phone to end recording, do nothing, reset flag
        self.recording_ended = False
        self.wait()
      else:
        self.r = None
        self.phoneStuck()

    threading.Thread(target=start_via_thread).start()
    self.message_count += 1

  def stopRecording(self):
    if self.r:
      self.recording_ended = True
      self.r.kill()
      self.r = None

  def playBeep(self):
    self.beep = subprocess.Popen(['aplay', 'beep.wav'])
    self.beep.wait()

  def phoneStuck(self):
    print("Phone Stuck!")
    self.state = 'phone-stuck'
    self.playBeep()
    time.sleep(1)
    self.handleGPIOEvent(GPIO.input(BUTTON_GPIO))


def get_usb_directory():
  process = subprocess.Popen("sudo cat /proc/mounts | grep sda1 | awk '{print $2}'", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
  out, err = process.communicate()
  return out.decode("UTF-8").strip()

# Create FSM object for tracking state
fsm = FSM(get_usb_directory())

def signal_handler(sig, frame):
  GPIO.cleanup()
  sys.exit(0)

if __name__ == '__main__':
  GPIO.setmode(GPIO.BCM)
  GPIO.setup(BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

  # Boot up sound
  subprocess.run(['aplay', 'sample-3s.wav'])

  GPIO.add_event_detect(BUTTON_GPIO, GPIO.BOTH, callback=lambda _: fsm.handleGPIOEvent(GPIO.input(BUTTON_GPIO)), bouncetime=500)

  signal.signal(signal.SIGINT, signal_handler)
  signal.pause()
