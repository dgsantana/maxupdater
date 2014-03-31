#!/usr/bin/python2.7
from __future__ import absolute_import, division, print_function, with_statement
from logging.handlers import RotatingFileHandler, NTEventLogHandler
import win32api
import time
import sys
import os
import win32service
import win32event
import servicemanager
import logging
from ConfigParser import NoOptionError, NoSectionError, SafeConfigParser
from psutil import NoSuchProcess
import win32serviceutil
import zmq
import threading
from zmq.eventloop import ioloop, zmqstream

__author__ = 'Daniel Santana'
__date__ = '30/01/2014'
__version__ = '1.5.0'
__status__ = 'Production'


class Signal(object):
    def __init__(self):
        self._handlers = []

    def connect(self, handler):
        self._handlers.append(handler)

    def fire(self, *args):
        for handler in self._handlers:
            handler(*args)


ioloop.install()


class MaxUpdaterService(win32serviceutil.ServiceFramework):
    """Max service update manager"""
    _svc_name_ = "3dsmaxupdatesvc"
    _svc_display_name_ = "3ds Max Updater Manager"
    _svc_description_ = "Manages automatic updates for 3ds max."

    updateCmdSignal = Signal()

    def __init__(self, args=None):
        if servicemanager.RunningAsService():
            sys.stdout = sys.stderr = open('nul', 'w')
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self._max_names = ["3dsmax.exe", "3dsmaxdesign.exe"]
        self._installs = ['maxplugins', 'dmaxplugins']
        self._services = {}
        self._max_versions = ['16']
        self._timeout = 5
        self._counter = 0
        self._first = True
        self._notify = None
        self._stopping = False
        self._log_level = logging.DEBUG
        self._logger = logging.getLogger('MaxUpdater')
        self._logger.setLevel(self._log_level)
        self._service_path = os.path.dirname(__file__) if not hasattr(sys, 'frozen') else os.path.dirname(unicode(sys.executable, sys.getfilesystemencoding()))
        self._options_files = {}
        self._default_path = os.path.join(self._service_path, 'updater.ini')
        self._options_files[self._default_path] = 0
        self.updateCmdSignal.connect(self.updater_cmd)

        from PluginUpdater import PluginUpdater

        self._updater = PluginUpdater(args=['-i'])
        self._updater.options_node = self._installs

        if servicemanager.RunningAsService():
            ev_net = NTEventLogHandler(self._svc_name_, None)
            ev_net.setLevel(logging.ERROR)
            ev_net.setFormatter(logging.Formatter('%(levelname)-8s %(message)s'))
            self._logger.addHandler(ev_net)
        else:
            logging.basicConfig()
        rl = RotatingFileHandler(os.path.join(self._service_path, 'debug.log'), delay=True, maxBytes=150000, backupCount=5)
        rl.setFormatter(logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s'))
        self._logger.addHandler(rl)

        self._logger.info('MaxUpdater Service {0} [{1}]'.format(__version__, __date__))
        self.read_settings()
        self._timeout = 3000
        self._exit_server = False
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.REP)
        import socket
        h = socket.gethostname().lower()
        self._socket.setsockopt(zmq.IDENTITY, h)
        self._socket.bind('tcp://*:5570')
        self._socket_pub = self._context.socket(zmq.PUB)
        self._socket_pub.bind('tcp://*:5571')
        self._server_stream = zmqstream.ZMQStream(self._socket)
        self._server_stream.on_recv(self._process_server)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop()
        win32event.SetEvent(self.hWaitStop)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)

    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
        try:
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self.start()
            win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
        except Exception:
            self._logger.error('Exeption', exc_info=True)
            self.SvcStop()

    def start(self):
        self._logger.info('Starting service.')
        server = self.start_server()
        while True:
            if self._stopping:
                self._logger.info('Stopping service.')
                ioloop.IOLoop.instance().stop()
                server.join()
                self._socket_pub.close()
                self._socket_pub = None
                break
            try:
                self.update_max()
            except:
                self._logger.debug('Error.', exc_info=True)
            time.sleep(self._timeout)

    def stop(self):
        self._stopping = True

    def start_server(self):
        t = threading.Thread(target=self.threaded_loop)
        t.daemon = True
        t.start()
        #context = zmq.Context.instance()
        #self._worker = context.socket(zmq.DEALER)
        return t

    @staticmethod
    def threaded_loop():
        print('Backoffice server started...')
        ioloop.IOLoop.instance().start()

    def _process_server(self, msg):
        #print(msg)
        import socket
        h = socket.gethostname().lower()
        if 'update' in msg:
            self._server_stream.send('Updating %s' % h)
            self.update_max()
        elif 'ping' in msg:
            #self._server_stream.send('info', zmq.SNDMORE)
            self._server_stream.send('%s is alive' % h)
            self._logger.info('Ping response sent.')
        elif 'quit' in msg:
            self._stopping = True
            self._logger.info('Requesting service stop.')
        else:
            self._logger.info('Unknowed message %s' % msg)

    def updater_cmd(self, cmd):
        try:
            self._server_stream.send(cmd)
            self._logger.info('Event sent to clients.')
        except:
            pass

    def standalone_loop(self):
        server = self.start_server()
        while 1:
            try:
                self.update_max()
                time.sleep(self._timeout)
            except:
                self._logger.info('Stopping service.')
                ioloop.IOLoop.instance().stop()
                server.join()
                break

    def _parse_options(self, option_file, global_options=False):
        if not os.path.exists(option_file):
            return
        m = os.path.getmtime(option_file)
        self._logger.debug('File %s modified %s' % (option_file, m))
        if not self._options_files.has_key(option_file) or self._options_files[option_file] != m:
            self._options_files[option_file] = m
        else:
            return
        if global_options:
            self._logger.info('Loading global ini %s' % option_file)
        else:
            self._logger.info('Loading ini %s' % option_file)
        config = SafeConfigParser()
        config.read(option_file)
        try:
            if config.has_option('Global', 'options') and not global_options:
                p = config.get('Global', 'options')
                self._parse_options(p, global_options=True)
            if config.has_option('Service', 'logging'):
                self._log_level = config.get('Service', 'logging')
                self._logger.setLevel(self._log_level)
            if config.has_option('Service', 'services'):
                self._services = eval(config.get('Service', 'services'))
            if config.has_option('Service', 'timer'):
                self._timeout = config.getint('Service', 'timer')
            if config.has_option('Service', 'maxprocesses'):
                self._max_names = [i.rstrip().lstrip() for i in config.get('Service', 'maxprocesses').split(',')]
            if config.has_option('Service', 'versions'):
                self._max_versions = [i.strip() for i in config.get('Service', 'versions').split(',')]
            if config.has_option('Service', 'installs'):
                self._installs = [i.strip() for i in config.get('Service', 'installs').split(',')]
                self._updater.options_node = self._installs
            if config.has_option('Service', 'repo'):
                self._updater._options.path = config.get('Service', 'repo')
                #self._logger.info('Plugin repo %s' % self._updater._options.path)
        except (NoSectionError, NoOptionError):
            pass

    def read_settings(self):
        """
        Read service settings
        """
        files = self._options_files.keys()
        for key in files:
            try:
                self._parse_options(key)
            except:
                self._logger.error('Error parsing %s.' % key, exc_info=True)
        self._first = False

    def can_update(self):
        import psutil

        abort = False
        try:
            plist = filter(lambda x: x.name in self._max_names,
                           [psutil.Process(i) for i in psutil.get_pid_list()])
            if not len(plist):
                return False

            for p in plist:
                perc = p.get_cpu_percent()
                self._logger.debug('3dsMax cpu usage %s' % perc)
                found_service = False
                for serv in self._services.itervalues():
                    if p.parent.name == serv and perc < 10.0:
                        self._logger.debug('Service found.')
                        found_service = True
                if not found_service:
                    self._logger.debug('Max found with parent %s.' % p.parent.name)
                    abort = True
        except NoSuchProcess:
            self._logger.debug('Parent not found.', exc_info=True)
            abort = True
        except Exception:
            self._logger.debug('Error.', exc_info=True)
        return abort

    def update_max(self):
        self.read_settings()

        if self.can_update():
            return
        self._logger.debug('No mission critical 3ds max running.')

        self._updater.load_updater_info()
        if not self._updater.check_for_valid_updates(self._max_versions):
            self._socket_pub.send_string('Updates not required.')
            self._logger.info('Updates not required.')
            return

        self._socket_pub.send_string('update_start')
        service_running = []
        for k in self._services.iterkeys():
            try:
                self._logger.info('%s service stopping...' % k)
                win32serviceutil.StopService(k)
                service_running.append(k)
            except:
                self._logger.debug('Error stopping %s.' % k, exc_info=True)

        try:
            self._logger.info('Updating...')
            self._updater.process_versions(self._max_versions)
        except:
            self._logger.error('Error updating.', exc_info=True)
            self._timeout = 60 * 3

        for k in service_running:
            try:
                self._logger.info('%s service starting...' % k)
                win32serviceutil.StartService(k)
            except:
                self._logger.error('Error starting %s.' % k, exc_info=True)

        self._logger.info('Update done.')
        self._socket_pub.send_string('update_end')


def ctrl_handler(ctrlType):
    return True


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'standalone':
        s = MaxUpdaterService()
        s.standalone_loop()
    else:
        win32api.SetConsoleCtrlHandler(ctrl_handler, True)
        win32serviceutil.HandleCommandLine(MaxUpdaterService)
