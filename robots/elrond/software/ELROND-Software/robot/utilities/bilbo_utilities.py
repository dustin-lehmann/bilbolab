from robot.communication.bilbo_communication import BILBO_Communication
from robot.hardware import get_hardware_definition
from utils.sound.sound import SoundSystem


# ======================================================================================================================
class BILBO_Utilities:
    sound_system: SoundSystem

    def __init__(self, communication: BILBO_Communication):
        hardware_definition = get_hardware_definition()
        if hardware_definition['electronics']['sound']['active']:
            self.sound_system = SoundSystem(hardware_definition['electronics']['sound']['gain'])
        else:
            self.sound_system = None

        self.communication = communication

        self.communication.wifi.addCommand(
            identifier='speak',
            callback=self.speak,
            arguments=['message'],
            description='Speak the given message'
        )

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

    # ------------------------------------------------------------------------------------------------------------------
    def speak(self, message):
        if self.sound_system is None:
            return
        self.sound_system.speak(message)

    # ------------------------------------------------------------------------------------------------------------------
