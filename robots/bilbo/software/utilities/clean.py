import argparse
import os
import glob

from core.utils.sound.sound import cleanTTS
from core.utils.logging_utils import Logger
from robot.paths import EXPERIMENTS_PATH

logger = Logger('Clean')


def clean_experiment_files():
    """Remove all experiment files from the experiments directory."""
    if not os.path.isdir(EXPERIMENTS_PATH):
        logger.warning(f"Experiments directory does not exist: {EXPERIMENTS_PATH}")
        return

    files = glob.glob(os.path.join(EXPERIMENTS_PATH, '*'))
    count = 0
    for f in files:
        if os.path.isfile(f):
            os.remove(f)
            count += 1
    logger.info(f"Removed {count} experiment file(s) from {EXPERIMENTS_PATH}")


def clean_tts_files():
    """Remove all cached TTS audio files."""
    cleanTTS()


def clean(experiment_files: bool = True, tts_files: bool = True):
    if experiment_files:
        clean_experiment_files()

    if tts_files:
        clean_tts_files()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Clean robot files')
    parser.add_argument('--experiments', action='store_true', help='Clean experiment files')
    parser.add_argument('--tts', action='store_true', help='Clean TTS cache files')
    parser.add_argument('--all', action='store_true', help='Clean everything')

    args = parser.parse_args()

    # If no specific flag is given, clean everything
    do_all = args.all or not (args.experiments or args.tts)

    clean(
        experiment_files=do_all or args.experiments,
        tts_files=do_all or args.tts,
    )
