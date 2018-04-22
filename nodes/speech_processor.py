#!/usr/bin/env python
import rospy
import rospkg
import pyaudio
from pocketsphinx.pocketsphinx import *
from sphinxbase.sphinxbase import *
from std_msgs.msg import String
from ownage_bot import *
from ownage_bot.msg import *
from ownage_bot.srv import *

class SpeechProcessor(object):
    """Processes natural speech to/from the syntax in DialogManager."""

    def __init__(self):
        # Pocketsphinx parameters
        pkg_path = rospkg.RosPack().get_path('ownage_bot')
        self.hmm_path = rospy.get_param("~hmm_path",
                                        pkg_path + "/speech/hmm")
        self.lm_path = rospy.get_param("~lm_path",
                                       pkg_path + "/speech/speech.lm")
        self.dict_path = rospy.get_param("~dict_path",
                                         pkg_path + "/speech/speech.dic")

        # PyAudio parameters
        self.audio_device_name = rospy.get_param("~audio_device_name",
                                                 "Samson RXD")
        self.audio_sample_rate = rospy.get_param("~audio_sample_rate",
                                                 16000)
        self.audio_buffer_size = rospy.get_param("~audio_buffer_size",
                                                 1024)

        # Initialize Pocketsphinx decoder
        config = Decoder.default_config()
        config.set_string('-hmm', self.hmm_path)
        config.set_string('-lm', self.lm_path)
        config.set_string('-dict', self.dict_path)
        config.set_string('-logfn', '/dev/null') # Suppress log msgs
        self.decoder = Decoder(config)
       
        # Initialize PyAudio and list device names
        pa = pyaudio.PyAudio()
        dev_names = [pa.get_device_info_by_index(i)['name'] for i in
                    range(pa.get_device_count())]
        # Default to first audio device
        dev_id = 0
        # Try to find input device that matches self.audio_device_name
        if self.audio_device_name is not None:
            for i, d in enumerate(dev_names):
                if self.audio_device_name.lower() in d.lower():
                    dev_id = i
        # Open audio stream from device
        self.stream = pa.open(format=pyaudio.paInt16, channels=1,
                              input=True, rate=self.audio_sample_rate,
                              frames_per_buffer=self.audio_buffer_size,
                              input_device_index=dev_id)

        # Publisher for commands recognized by DialogManager
        self.speech_cmd_pub = rospy.Publisher("speech_cmd", 
                                              String, queue_size=10)

    def process_stream(self):
        """Continuously process audio stream until shutdown."""
        self.stream.start_stream()
        self.decoder.start_utt()
        speech_detected = False
        while not rospy.is_shutdown():
            buf = self.stream.read(self.audio_buffer_size,
                                   exception_on_overflow=False)
            if buf:
                self.decoder.process_raw(buf, False, False)
                # Check if speech detection status has changed
                if self.decoder.get_in_speech() != speech_detected:
                    speech_detected = self.decoder.get_in_speech()
                    # Terminate and process utterance upon silence
                    if not speech_detected:
                        self.decoder.end_utt()
                        self.parse_utterance()
                        self.decoder.start_utt()
            else:
                break

    def parse_utterance(self):
        """Parse decoded utterances."""
        if self.decoder.hyp() is None:
            return
        utt = self.decoder.hyp().hypstr.lower()
        print utt

        for parse_f in [self.parse_as_action]:
            msg = parse_f(utt)
            if msg is not None:
                self.speech_cmd_pub.publish(msg)

    def parse_as_action(self, utt):
        if utt in ["stop", "cancel"]:
            return "cancel"
        else return None

if __name__ == '__main__':
    rospy.init_node('speech_processor')
    speech_processor = SpeechProcessor()
    speech_processor.process_stream()
