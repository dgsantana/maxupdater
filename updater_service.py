import logging
from logging.handlers import RotatingFileHandler, NTEventLogHandler
import os
import sys
import win32api
import win32service
import win32event
import servicemanager
import win32serviceutil
from core.cmd import ExecThread
from core.update import UpdateThread

__author__ = 'dgsantana'


class MaxUpdaterService(win32serviceutil.ServiceFramework):
    def __init__(self, args=None):
        if servicemanager.RunningAsService():
            sys.stdout = sys.stderr = open('nul', 'w')
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self._logger = logging.getLogger('MaxUpdater')
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
        self._cmd_thread = ExecThread()
        self._update_thread = UpdateThread()

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
            self._logger.error('Exception', exc_info=True)
            self.SvcStop()

    def stop(self):
        self._cmd_thread.stop()
        self._update_thread.stop()
        if self._cmd_thread.is_alive:
            self._cmd_thread.join()
        if self._update_thread.is_alive:
            self._update_thread.join()

    def start(self):
        self._cmd_thread.start()
        self._update_thread.start()


def ctrl_handler(ctrlType):
    return True


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'standalone':
        s = MaxUpdaterService()
        s.standalone_loop()
    else:
        win32api.SetConsoleCtrlHandler(ctrl_handler, True)
        win32serviceutil.HandleCommandLine(MaxUpdaterService)