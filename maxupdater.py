#!/usr/bin/python2.7
import logging
import time
import sys
from core.cmd import ExecThread
from core.update import UpdateThread

__author__ = 'Daniel Santana'


class StandaloneUpdater(object):
    def __init__(self):
        self._logger = logging.getLogger('MaxUpdater')
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self._logger.addHandler(ch)
        self._cmd_thread = ExecThread()
        self._update_thread = UpdateThread()

    def stop(self):
        self._cmd_thread.exit_flag = True
        self._update_thread.exit_flag = True
        self._cmd_thread.join()
        self._update_thread.join()

    def start(self):
        self._cmd_thread.start()
        self._update_thread.start()
        while True:
            try:
                time.sleep(15)
            except KeyboardInterrupt:
                self._logger.debug('Ctrl+C detected.')
                break
        self._cmd_thread.stop()
        self._update_thread.stop()
        if self._cmd_thread.is_alive:
            self._cmd_thread.join()
            self._logger.debug('Command thread stopped.')
        if self._update_thread.is_alive:
            self._update_thread.join()
            self._logger.debug('Updater thread stopped.')
        self._logger.debug('Clean exit from Ctrl+C')
        sys.exit()

if __name__ == '__main__':
    s = StandaloneUpdater()
    s.start()