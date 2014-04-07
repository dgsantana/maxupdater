from sys import exc_info
import threading
import socket
import zmq
from subprocess import call
import logging

__author__ = 'dgsantana'
__version__ = '1.0a'
__date__ = '31/03/2014'


class ExecThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self._stop = threading.Event()
        self._logger = logging.getLogger('MaxUpdater')
        self._logger.info('Cmd Thread {0} [{1}]'.format(__version__, __date__))
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.REP)
        self._socket.setsockopt(zmq.IDENTITY, socket.gethostname().lower())
        self._failed = False
        try:
            self._socket.bind('tcp://*:56800')
        except:
            self._logger.error('Error creating socket.', exc_info=True)
            self._failed = True

    def run(self):
        if self._failed:
            return
        poller = zmq.Poller()
        poller.register(self._socket, zmq.POLLIN)
        while not self._stop.isSet():
            socks = poller.poll(1000)
            if self._socket in socks and socks[self._socket] == zmq.POLLIN:
                cmd = self._socket.recv()
                self._logger.debug('Received command %s' % cmd)
                if cmd == 'EXEC':
                    args = self._socket.recv()
                    ret = call(args, shell=True)
                    self._socket.send('returned %s' % ret)
                else:
                    self._socket.send('OK')

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()