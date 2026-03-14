from typing import Union

from core.communication.wifi.data_link import CommandArgument
from core.utils.callbacks import Callback
from hardware.control_board import RobotControl_Board
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from core.utils.events import event_definition, Event
from core.utils.sound.sound import SoundSystem, EdgeTTSVoiceEngine, VOICE_PRESETS


@event_definition
class BILBO_Utilities_Events:
    resume: Event


# ======================================================================================================================
class BILBO_Utilities:
    sound_system: Union[SoundSystem, None]
    core: BILBO_Common

    board: RobotControl_Board

    def __init__(self, core: BILBO_Common,
                 board: RobotControl_Board,
                 communication: BILBO_Communication,
                 sound_settings=None):

        self.core = core
        self.board = board

        config = self.core.config

        if config.electronics.sound.active:
            volume = sound_settings.volume if sound_settings else 0.5
            voice = sound_settings.voice if sound_settings else 'female'
            preset = VOICE_PRESETS.get(voice, VOICE_PRESETS['female'])
            engine = EdgeTTSVoiceEngine(voice=preset['voice'])
            self.sound_system = SoundSystem(volume=volume,
                                            primary_engine=engine,
                                            add_robot_filter=preset['robot_filter'])
        else:
            self.sound_system = None

        self.communication = communication
        self.events = BILBO_Utilities_Events()

        self.communication.wifi.callbacks.connected.register(self.board.setStatusLed, inputs={'state': True},
                                                             discard_inputs=True)
        self.communication.wifi.callbacks.disconnected.register(self.board.setStatusLed, inputs={'state': False},
                                                                discard_inputs=True)

        self.communication.wifi.newCommand(
            identifier='speak',
            function=self.speak,
            arguments=['message'],
            description='Speak the given message'
        )

        self.communication.wifi.newCommand(identifier='rgbled',
                                           function=self.setLEDs,
                                           arguments=['red', 'green', 'blue'],
                                           description='')

        self.communication.wifi.newCommand(identifier='beep',
                                           function=self.beep,
                                           description='',
                                           arguments=[
                                               CommandArgument(name='frequency',
                                                               type=str,
                                                               optional=True,
                                                               default='medium',
                                                               description='Frequency of the beep. Can be "low", "medium", "high" or a number in Hz'),
                                               CommandArgument(name='time_ms',
                                                               type=int,
                                                               optional=True,
                                                               default=500,
                                                               description='Duration of the beep in ms'),
                                               CommandArgument(name='repeats',
                                                               type=int,
                                                               optional=True,
                                                               default=1,
                                                               description='Number of repeats')
                                           ])

        # Add some utility speech output
        self.core.events.joystick_connected.on(callback=Callback(self.speak,
                                                                 inputs={'message': 'Joystick connected'},
                                                                 discard_inputs=True),
                                               discard_data=True,
                                               )

        self.core.events.joystick_disconnected.on(callback=Callback(self.speak,
                                                                    inputs={'message': 'Joystick disconnected'},
                                                                    discard_inputs=True),
                                                  discard_data=True, )

        # ------------------------------------------------------------------------------------------------------------------

    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        if self.sound_system is not None:
            self.sound_system.start()

    # ------------------------------------------------------------------------------------------------------------------
    def playTone(self, tone):
        if self.sound_system is None:
            return
        self.sound_system.play(tone)

    # ------------------------------------------------------------------------------------------------------------------
    def setLEDs(self, red, green, blue):
        self.board.setRGBLEDExtern([red, green, blue])

    # ------------------------------------------------------------------------------------------------------------------
    def beep(self, frequency, time_ms, repeats):
        self.board.beep(frequency, time_ms, repeats)

    # ------------------------------------------------------------------------------------------------------------------
    def speak(self, message, on_host=True):
        if self.sound_system is None:
            if on_host:
                self.communication.wifi.sendEvent(event='speak',
                                                  data={
                                                      'message': message,

                                                  })
        else:
            self.sound_system.speak(message)
