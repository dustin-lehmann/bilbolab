from core.utils.logging_utils import Logger

if __name__ == '__main__':
    logger = Logger('test', 'DEBUG')

    Logger.section('Section 1')
    logger.info('This is an info message')

    Logger.section('Section 2')
    logger.info('This is another info message')
