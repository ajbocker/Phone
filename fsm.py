import subprocess
import threading
from datetime import datetime

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

class FSM:
  def __init__(self):
    self.state = 'waiting'
    self.transitions = {
      ('waiting', False): self.play,
      ('playing', True): self.stopPlayback,
      ('playing', False): self.record,
      ('recording', True): self.stopRecording
    }

  def handleGPIOEvent(self, phone_down):
    if (self.state, phone_down) in self.transitions:
      self.transitions[(self.state, phone_down)]()

  def play(self):
    print("Playing!")
    self.state = 'playing'
    # Start pre-recorded message via command
    def start_via_thread():
      self.p = subprocess.Popen(['aplay', 'sample-3s.wav'])
      returncode = self.p.wait()
      if returncode == 0:
        # Playback finished completely
        self.record()
      else:
        # Playback cancelled
        self.wait()

    threading.Thread(target=start_via_thread).start()

  def stopPlayback(self):
    self.p.kill()

  def wait(self):
    print("Waiting!")
    self.state = 'waiting'

  def record(self):
    print("Recording!")
    self.state = 'recording'
    filename = "recordings/" + datetime.now().strftime("%d-%b-%Y_%H-%M-%S") + "_recording.wav"
    # Start recording via command
    def start_via_thread():
      self.r = subprocess.Popen(['arecord', '--device=hw:1,0', '--format', 'S16_LE', '--rate', '44100', '-c1', filename])
      self.r.wait()
      self.wait()

    threading.Thread(target=start_via_thread).start()

  def stopRecording(self):
    self.r.kill()
