Maxupdater
==========

3dsMax plugin updater

Collection of python scripts with support for running as a service (pywin32).

Current features:
- backup and restore mode (use a workstation for "backup" to central repo)
- file list
- env variables, get and set
- registry variables
- ini updating
- multiple versions

TODO:
- integrate with maxplus (started with pyzmq -> not working)
- better support for max design
- better support for multiple max versions (separate file lists)


This project, makes use of:
- pyzmq (future comunication with UI and network shell)
- pyside (for future tray UI)
- pywin32 (services)
- psutil (process access)

Builds of this libraries can be found in the great repository of Christoph Gohlke at http://www.lfd.uci.edu/~gohlke/pythonlibs/.
