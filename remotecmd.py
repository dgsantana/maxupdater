#!/usr/bin/python2.7
#encoding: utf-8
import sys
import zmq
import socket
from time import sleep
import threading
from zmq.eventloop import ioloop, zmqstream

__author__ = 'Daniel Santana'
__version__ = '1.0'
__copyright__ = 'Copyright 2014, pyResCam'
__date__ = '31-01-2014'

ioloop.install()


class RemoteCmd(object):
    def __init__(self):
        self.servers_list = []
        context = zmq.Context()
        self._api = context.socket(zmq.REQ)
        self._info = context.socket(zmq.SUB)
        #socket.connect('tcp://127.0.0.1:5570')
        #self.client_stream = zmqstream.ZMQStream(sock, ioloop.IOLoop.instance())
        #self.client_stream.on_recv(self.process_response)
        self._stop = False
        self._info_thread = threading.Thread(target=self.info_loop, args=[self])
        self._info_thread.daemon = True
        self.daemon = threading.Thread(target=self.threaded_loop, args=[self])
        self.daemon.daemon = True
        self.daemon.start()
        self._info_thread.start()

    @staticmethod
    def info_loop(self):
        print('Info thread started...\n')
        while 1:
            if self._stop:
                return
            self._info.poll()
            message = self._info.recv()
            if message != '':
                print message

    @staticmethod
    def threaded_loop(self):
        print('Backoffice server started...\n')
        while 1:
            if self._stop:
                return
            self._api.poll()
            message = self._api.recv()
            if message != '':
                print message
            sleep(.5)
        #ioloop.IOLoop.instance().start()

    def shutdown(self):
        print 'Quit'
        #ioloop.IOLoop.instance().stop()
        #self.client_stream.socket.setsockopt(zmq.LINGER, 0)
        #self.client_stream.socket.close()
        #self.client_stream.close()
        #self.client_stream = None
        self._stop = True
        self.daemon.join()
        self._info_thread.join()
        sys.exit()

    def parse_cmd(self, cmdline):
        cmdline = cmdline.strip('\r\n')
        cmd, opt = cmdline.partition(' ')[::2]
        message = ''
        if cmd == 'add':
            ipadd = socket.gethostbyname(opt)
            self.servers_list.append('{0} - {1}'.format(opt, ipadd))
            self._api.connect('tcp://%s:5570' % ipadd)
            self._info.connect('tcp://%s:5571' % ipadd)
        elif cmd == 'update':
            if opt == '' or opt == 'all':
                print 'Updating %i clients' % len(self.servers_list)
                #for i in xrange(len(self.servers_list)):
                self._api.send_string('update')
                #message = self._api.recv(zmq.NOBLOCK)
        elif cmd == 'ping':
            if opt == '' or opt == 'all':
                print 'Pinging %i clients' % len(self.servers_list)
                #for i in xrange(len(self.servers_list)):
                self._api.send_string('ping')
                #message = self._api.recv(zmq.NOBLOCK)
        elif cmd == 'quit':
            self.shutdown()
        elif cmd == 'list':
            print 'Listing clients'
            for server in self.servers_list:
                print server
        elif cmd != '':
            print 'Command {0} error.'.format(cmd)

    def process_response(self, cmd):
        print 'Response' % cmd


if __name__ == '__main__':
    print 'Rmote updater cmdline v%s' % __version__
    rmt = RemoteCmd()
    while 1:
        cmdline = raw_input('Server command: ')
        rmt.parse_cmd(cmdline)
