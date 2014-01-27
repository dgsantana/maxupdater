from __future__ import print_function, absolute_import, with_statement, unicode_literals, division, generators
import zmq
from zmq.eventloop import zmqstream

__author__ = 'dgsantana'
__version__ = ''
__copyright__ = 'Copyright 2013, pyResCam'
__date__ = '03-10-2013'


_context = zmq.Context().instance()
_socket = _context.socket(zmq.ROUTER)
_socket.bind('tcp://127.0.0.1:5570')
_server_stream = zmqstream.ZMQStream(_socket)
_server_stream.on_recv(_process_server)


def _process_server(msg):
    print(msg)
    if 'update -force' in msg:
        update_max()
    elif 'ping' in msg:
        import socket
        h = socket.gethostname().lower()
        _server_stream.send('info', zmq.SNDMORE)
        _server_stream.send('%s is alive' % h)
        print('Ping response sent.')
    else:
        print('Unknowed message %s' % msg)