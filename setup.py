#!/usr/bin/python2.7
from distutils.core import setup
import py2exe, sys, os
from py2exe.build_exe import Target
import zmq

os.environ['PATH'] = os.environ['PATH'] + os.pathsep + os.path.split(zmq.__file__)[0]

maxupdaterservice = Target(
    modules=['MaxUpdaterService'],
    cmdline_style='pywin32'
)

updater_service = Target(
    modules=['updater_service'],
    cmdline_style='pywin32'
)

setup(options=
      dict(py2exe={"bundle_files": 3,
                   'compressed': 1,
                   'optimize': 2,
                   'dll_excludes': ['MSVCP90.dll']
      }),
      zipfile='lib/shared.zip',
      service=[maxupdaterservice, updater_service],
      console=[{'script': "PluginUpdater.py"}, {'script': "UpdaterCmds.py"}, {'script': "maxupdater.py"}],
      requires=['psutil', 'clint'])
