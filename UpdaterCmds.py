#encoding: utf-8
from __future__ import absolute_import, division, print_function, with_statement
import threading
from time import sleep
from PySide.QtCore import QThread, Signal, QMutexLocker, QMutex
import zmq
from PySide import QtGui, QtCore
from zmq.eventloop import zmqstream, ioloop

__author__ = 'dgsantana'
__version__ = ''
__copyright__ = 'Copyright 2013, pyResCam'
__date__ = '27-09-2013'

ioloop.install()


class UpdaterWindow(QtGui.QDialog):
    def __init__(self):
        super(UpdaterWindow, self).__init__()

        import UpdaterCmds_ui

        self.ui = UpdaterCmds_ui.Ui_Form()
        self.ui.setupUi(self)
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)

        self.minimizeAction = QtGui.QAction("Mi&nimize", self, triggered=self.hide)
        self.restoreAction = QtGui.QAction("&Restore", self, triggered=self.showNormal)
        self.quitAction = QtGui.QAction("&Quit", self, triggered=self.terminate)

        self.trayIconMenu = QtGui.QMenu(self)
        self.trayIconMenu.addAction(self.minimizeAction)
        self.trayIconMenu.addAction(self.restoreAction)
        self.trayIconMenu.addSeparator()
        self.trayIconMenu.addAction(self.quitAction)

        self.tray_icon = QtGui.QSystemTrayIcon(self)
        self.tray_icon.setContextMenu(self.trayIconMenu)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/updater/tray"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.tray_icon.setIcon(icon)

        self.tray_icon.show()

        #self.server = UpdaterClient()
        #self.server.start()
        #self.server.sigMessage.connect(self.showMessage)
        #self.server.sigUpdateStart.connect(self.warning_update)
        #self.server.sigUpdateEnd.connect(self.hide)

        self._run_threads = True
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.DEALER)
        self._socket.connect('tcp://127.0.0.1:5570')

        self._client_stream = zmqstream.ZMQStream(self._socket)
        self._client_stream.on_recv(self._process_server)

        self._client = threading.Thread(target=self.threaded_loop)
        self._client.daemon = True
        self._client.start()

        self._server_pinger = threading.Thread(target=self._pinger)
        self._server_pinger.start()

    def threaded_loop(self):
        while self._run_threads:
            print('Starting Client...')
            ioloop.IOLoop.instance().start()

    def _pinger(self):
        while self._run_threads:
            print('ping')
            self._client_stream.send('ping')
            sleep(2)

    def _process_server(self, cmd):
        print(cmd)
        if cmd == 'info':
            print('info')
            msg = cmd[1]
            self.sigMessage.emit(msg)
        elif cmd == 'update_start':
            self.sigUpdateStart.emit(self)
        elif cmd == 'update_end':
            self.sigUpdateEnd.emit(self)

    def terminate(self):
        self._run_threads = False
        self._server_pinger.join()
        ioloop.IOLoop.instance().stop()
        self._client.join()
        QtGui.qApp.quit()

    def warning_update(self):
        self.showMessage(u'Está a decorrer uma atualização do 3ds Max. Aguardem...')
        self.show()

    def showMessage(self, msg):
        icon = QtGui.QSystemTrayIcon.MessageIcon
        self.tray_icon.showMessage('Aviso', msg, icon, 5.0 * 1000)


class UpdaterClient(QThread):
    sigMessage = Signal(str)
    sigUpdateStart = Signal(object)
    sigUpdateEnd = Signal(object)

    def __init__(self):
        super(UpdaterClient, self).__init__()
        self.locker = QMutex()
        self._end_now = False
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.DEALER)
        self._socket.connect('tcp://127.0.0.1:5570')
        self._server_stream = zmqstream.ZMQStream(self._socket)
        self._server_stream.on_recv(self._process_server)
        self._server = threading.Thread(target=ioloop.IOLoop.instance().start)
        self._stopped = False

    def stop(self):
        self._stopped = True

    def _process_server(self, cmd):
        print(cmd)
        if cmd == 'info':
            print('info')
            msg = cmd[1]
            self.sigMessage.emit(msg)
        elif cmd == 'update_start':
            self.sigUpdateStart.emit(self)
        elif cmd == 'update_end':
            self.sigUpdateEnd.emit(self)

    def run(self):
        self._server.start()

        while not self._stopped:
            # Wait for something
            self._server_stream.send('ping')
            sleep(2)

        ioloop.IOLoop.instance().stop()
        self._server.join()
        self._socket.close()
        self._context.term()


if __name__ == '__main__':

    import sys

    app = QtGui.QApplication(sys.argv)

    if not QtGui.QSystemTrayIcon.isSystemTrayAvailable():
        QtGui.QMessageBox.critical(None, "Systray", "I couldn't detect any system tray on this system.")
        sys.exit(1)

    QtGui.QApplication.setQuitOnLastWindowClosed(False)

    window = UpdaterWindow()
    #window.show()
    sys.exit(app.exec_())