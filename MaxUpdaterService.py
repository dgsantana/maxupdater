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
__date__ = '20/09/2013'
__version__ = '1.2.5'
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
        #self._spawner = False
        #self._spwanerSvc = False
        #self._spwanerPath = None
        #self._spwanerPid = 0
        self._max_names = ["3dsmax.exe", "3dsmaxdesign.exe"]
        #self._spawner_name = 'vrayspawner2013.exe'
        #self._spawner_svc_name = 'vrayspawner 2013'
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
        self._service_path = os.path.dirname(__file__)
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
        rl = RotatingFileHandler('c:/Tools/Updater/debug.log', delay=True, maxBytes=150000, backupCount=5)
        rl.setFormatter(logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s'))
        self._logger.addHandler(rl)

        self._logger.info('MaxUpdater Service {0} [{1}]'.format(__version__, __date__))
        self.read_settings()
        self._timeout = 3000
        self._exit_server = False
        #self._threadLock = threading.Lock()
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.ROUTER)
        self._socket.bind('tcp://127.0.0.1:5570')
        self._server_stream = zmqstream.ZMQStream(self._socket)
        self._server_stream.on_recv(self._process_server)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop()
        win32event.SetEvent(self.hWaitStop)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)

    def SvcDoRun(self):
        #servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
        #                      servicemanager.PYS_SERVICE_STARTED,
        #                      (self._svc_name_, ''))
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
                break
            self.update_max()
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
        print(msg)
        if 'update -force' in msg:
            self.update_max()
        elif 'ping' in msg:
            import socket
            h = socket.gethostname().lower()
            self._server_stream.send('info', zmq.SNDMORE)
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

    def read_settings(self):
        """
        Read service settings
        """
        p = r'\\4arq-server00\netinstall\max_plugs\updater.ini'
        if os.path.exists(p):
            m = os.path.getmtime(p)
            if self._notify != m:
                self._notify = m
            else:
                return
            self._logger.info('Loading ini')
            c = SafeConfigParser()
            c.read(p)
            try:
                if c.has_option('Service', 'logging'):
                    self._log_level = c.get('Service', 'logging')
                    self._logger.setLevel(self._log_level)
                #if c.has_option('Service', 'vrayspawner'):
                #    self._spawner_name = c.get('Service', 'vrayspawner')
                if c.has_option('Service', 'services'):
                    self._services = eval(c.get('Service', 'services'))
                if c.has_option('Service', 'timer'):
                    self._timeout = c.getint('Service', 'timer')
                #if c.has_option('Service', 'vrayspawnersvc'):
                #    self._spawner_svc_name = c.get('Service', 'vrayspawnersvc')
                if c.has_option('Service', 'maxprocesses'):
                    self._max_names = [i.rstrip().lstrip() for i in c.get('Service', 'maxprocesses').split(',')]
                if c.has_option('Service', 'versions'):
                    self._max_versions = [i.strip() for i in c.get('Service', 'versions').split(',')]
                if c.has_option('Service', 'installs'):
                    self._installs = [i.strip() for i in c.get('Service', 'installs').split(',')]
                    self._updater.options_node = self._installs
                if c.has_option('Service', 'repo'):
                    self._updater.options.path = c.get('Service', 'repo')
            except (NoSectionError, NoOptionError):
                pass
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
                        self._logger.info('Service found.')
                        found_service = True
                if not found_service:
                    self._logger.info('Max found with parent %s.' % p.parent.name)
                    abort = True
        except NoSuchProcess:
            self._logger.debug('Parent not found.', exc_info=True)
            abort = True
        return abort

    def update_max(self):
        self.read_settings()

        if self.can_update():
            return
        self._logger.debug('No mission critical 3ds max running.')

        self._updater.load_updater_info()
        if not self._updater.check_for_valid_updates(self._max_versions):
            self._logger.info('Updates not required.')
            return

        self.updateCmdSignal.fire('update_start')
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
        self.updateCmdSignal.fire('update_end')


def ctrl_handler(ctrlType):
    return True


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'standalone':
        s = MaxUpdaterService()
        s.standalone_loop()
    else:
        win32api.SetConsoleCtrlHandler(ctrl_handler, True)
        win32serviceutil.HandleCommandLine(MaxUpdaterService)
