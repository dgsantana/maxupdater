from ConfigParser import NoSectionError, NoOptionError, SafeConfigParser, ConfigParser
import os
from os.path import join, dirname
import _winreg
import socket
import time
import sys

from psutil import NoSuchProcess
import psutil
import win32serviceutil
import yaml

from dsutils import GetHashofDirs, delete_files, copy_files


__author__ = 'dgsantana'
__version__ = '2.0a'
__date__ = '31/03/2014'

import threading
import logging

try:
    from clint.textui import progress
except ImportError:
    pass

if "progress" in dir():
    DONT_USE_PROGRESS = False
else:
    DONT_USE_PROGRESS = True


class UpdateThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self._monitor_processes = True
        self._options_files = {}
        self._service_path = os.path.dirname(__file__) if not hasattr(sys, 'frozen') else os.path.dirname(
            unicode(sys.executable, sys.getfilesystemencoding()))
        self._default_path = os.path.join(self._service_path, 'updater.ini')
        self._options_files[self._default_path] = 0
        self._first = True
        self._notify = None
        self._options = {'timeout': 900, 'all_nodes': False, 'mode': 'install'}
        self._plugin_list = {}
        self._env = {'$host': socket.gethostname().lower()}
        self._options['backup_info'] = '$host_$node.id'
        self._options['max_timeout'] = 600
        self._stop = threading.Event()
        self._logger = logging.getLogger('MaxUpdater')
        self._logger.info('Updater Thread {0} [{1}]'.format(__version__, __date__))

    def run(self):
        while not self._stop.isSet():
            self._update_max()
            time.sleep(self._options['timeout'])

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

    def _load_updater_info(self):
        f = join(self._options['repo'], 'plugins.yaml')
        if os.path.exists(f):
            m = os.path.getmtime(f)
            if self._notify != m:
                self._notify = m
            else:
                return
            self._logger.info('Loading updater info.')
            self._plugin_list = yaml.load(open(f))

    def _parse_options(self, option_file, global_options=False):
        if not os.path.exists(option_file):
            return
        m = os.path.getmtime(option_file)
        if not self._options_files.has_key(option_file) or self._options_files[option_file] != m:
            self._logger.debug('File %s modified %s' % (option_file, m))
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
            if config.has_option('Global', 'mode') and not global_options:
                self._options['mode'] = config.get('Global', 'mode')
            if config.has_option('Service', 'logging'):
                self._options['logging'] = config.get('Service', 'logging')
                self._logger.setLevel(self._options['logging'])
            if config.has_option('Service', 'services'):
                self._options['services'] = eval(config.get('Service', 'services'))
            if config.has_option('Service', 'timer'):
                self._options['timeout'] = config.getint('Service', 'timer')
            if config.has_option('Service', 'processes'):
                self._options['processes'] = [i.rstrip().lstrip() for i in
                                              config.get('Service', 'processes').split(',')]
            if config.has_option('Service', 'versions'):
                self._options['versions'] = [i.strip() for i in config.get('Service', 'versions').split(',')]
            if config.has_option('Service', 'installs'):
                self._options['installs'] = [i.strip() for i in config.get('Service', 'installs').split(',')]
            if config.has_option('Service', 'repo'):
                self._options['repo'] = config.get('Service', 'repo')
            if config.has_option('Service', 'maxtimeout'):
                self._options['maxtimeout'] = config.get('Service', 'maxtimeout')
        except (NoSectionError, NoOptionError):
            pass

    def _read_settings(self):
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

    def _can_update(self):
        abort = False
        try:
            plist = filter(lambda x: x.name in self._options['processes'],
                           [psutil.Process(i) for i in psutil.get_pid_list()])
            if not len(plist):
                return False

            for p in plist:
                per = p.get_cpu_percent()
                self._logger.debug('3dsMax cpu usage %s' % per)
                found_service = False
                for service_name in self._options['services'].itervalues():
                    if p.parent.name == service_name and per < 10.0:
                        self._logger.debug('Service found.')
                        found_service = True
                if not found_service:
                    self._logger.debug('%s parent %s.' % (p.name, p.parent.name))
                    abort = True
        except NoSuchProcess:
            self._logger.debug('Parent not found.', exc_info=True)
            abort = True
        except Exception:
            self._logger.debug('Error.', exc_info=True)
        return abort

    def _is_process_running(self, processes_to_check, services):
        abort = False
        if not isinstance(processes_to_check, list):
            raise Exception('Requires a list, got %s' % type(processes_to_check))
        if not isinstance(services, dict):
            raise Exception('Requires a dict, got %s' % type(services))
        if len(processes_to_check) == 0:
            return False
        try:
            import win32com.client
            wmi = win32com.client.GetObject('winmgmts:')
            for p in wmi.InstancesOf('win32_process'):
                if not p.name in processes_to_check:
                    continue
                ps = psutil.Process(p.ProcessId)
                per = 0
                try:
                    per = ps.get_cpu_percent()
                except:
                    pass
                self._logger.debug('%s cpu usage %s' % (p.name, per))
                parents = wmi.ExecQuery('Select * from win32_process where ProcessId=%s' % p.ParentProcessId)
                found_service = False
                for service_name in services.itervalues():
                    for parent in parents:
                        if parent.name == service_name and per < 10.0:
                            self._logger.info('Service %s found.' % parent.name)
                            found_service = True
                if not found_service:
                    self._logger.info('%s has a diferent. [%s.]' % (p.name, parents[0].name))
                    abort = True
            # for p in psutil.process_iter():
            #     try:
            #         if not p.name() in processes_to_check:
            #             continue
            #         per = p.get_cpu_percent()
            #         self._logger.debug('%s cpu usage %s' % (p.name(), per))
            #         found_service = False
            #         for service_name in services.itervalues():
            #             if p.parent().name() == service_name and per < 10.0:
            #                 self._logger.info('Service found.')
            #                 found_service = True
            #         if not found_service:
            #             self._logger.info('%s parent %s.' % (p.name(), p.parent().name()))
            #             abort = True
            #     except:
            #         self._logger.log(1, 'Access denied.', exc_info=True)
        except NoSuchProcess:
            self._logger.debug('Parent not found.', exc_info=True)
            abort = True
        except Exception:
            self._logger.error('Error.', exc_info=True)
            abort = True
        return abort

    def _update_max(self):
        self._read_settings()

        #if self._can_update():
        #    return
        #self._logger.debug('No mission critical 3ds max running.')

        self._load_updater_info()
        nodes_required = list(set(self._check_for_valid_updates(self._options['versions'])))
        if len(nodes_required) == 0:
            self._logger.debug('Updates not required.')
            return

        # service_running = []
        # for k in self._options['services'].iterkeys():
        #     try:
        #         self._logger.info('%s service stopping...' % k)
        #         win32serviceutil.StopService(k)
        #         service_running.append(k)
        #     except:
        #         self._logger.debug('Error stopping %s.' % k, exc_info=True)

        # don't let any of the processes run
        # killer = threading.Thread(target=self._process_killer)
        # self._monitor_processes = True
        # killer.start()
        completed = False
        try:
            self._logger.info('Updating... %s' % nodes_required)
            completed = self._process_versions(nodes_required)
        except:
            self._logger.error('Error updating.', exc_info=True)

        if not completed and self._options['timeout'] < self._options['max_timeout']:
            self._options['timeout'] += 60

        # self._monitor_processes = False
        # killer.join()
        # for k in service_running:
        #     try:
        #         self._logger.info('%s service starting...' % k)
        #         win32serviceutil.StartService(k)
        #     except:
        #         self._logger.error('Error starting %s.' % k, exc_info=True)
        self._logger.info('Update done.')

    def _set_env(self, env_key):
        for k, v in env_key.iteritems():
            if v[0] == 'setenv':
                name = self._parse_env(v[1])
                value = self._parse_env(v[2])
                path = r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
                reg = _winreg.ConnectRegistry(None, _winreg.HKEY_LOCAL_MACHINE)
                key = _winreg.OpenKey(reg, path, 0, _winreg.KEY_ALL_ACCESS)
                _winreg.SetValueEx(key, name, 0, _winreg.REG_EXPAND_SZ, value)
                self._logger.info('Setting env: %s=%s' % (name, value))
            elif v[0] == 'setreg':
                path = self._parse_env(v[1])
                name = self._parse_env(v[2])
                value = self._parse_env(v[3])
                self._set_reg(path, name, value)
                self._logger.info('Setting Registry: %s[%s]=%s' % (path, name, value))

    def _update_env(self, d):
        """
        @type d: dict
        @param d:
        @return:
        """
        result = True
        for k, v in d.iteritems():
            if v[0] == 'reg':
                self._env[k] = self._get_reg(self._parse_env(v[1]), self._parse_env(v[2]))
                if self._env[k] is None:
                    result = False
                else:
                    pass  # self._logger.debug("Adding env['%s'] = '%s'" % (k, self._env[k]))
        return result

    @staticmethod
    def _get_reg(hkey, query):
        """
        Get info from Registry
        @param hkey: HKey
        @param query: Local key
        @return: the Value of the Key
        """
        try:
            with _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, hkey) as key:
                result = _winreg.QueryValueEx(key, query)[0]
        except:
            result = None
        return result

    @staticmethod
    def _set_reg(hkey, query, value):
        """
        Set info from Registry
        @param hkey: HKey
        @param query: Local key
        @param: value: Value of the Key
        """
        try:
            with _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, hkey) as key:
                result = _winreg.SetValueEx(key, query, 0, _winreg.REG_SZ, value)
        except:
            result = None
        return result

    def _parse_env(self, s):
        for k, v in self._env.iteritems():
            if v is not None:
                s = s.replace(k, v)
        return s

    def copy_files(self, backup_dst, base_dir, build_number, files):
        """
        Copies files
        :type build_number: str
        :type base_dir: str
        :type backup_dst: str
        :param backup_dst:
        :param base_dir:
        :param build_number:
        :param files:
        :type files: list
        """
        mode = self._options['mode']
        file_count = 0
        if DONT_USE_PROGRESS:
            it = files
        else:
            it = progress.bar(files)
        for s in it:
            if mode == 'backup':
                dst = join(backup_dst, build_number, s)
                dst_path = dirname(dst)
                src = join(base_dir, s)
            elif mode == 'install':
                src = join(backup_dst, build_number, s)
                dst = join(base_dir, s)
                dst_path = dirname(dst)
            try:
                os.makedirs(dirname(dst))
            except WindowsError as e:
                pass
                ## self._logger.error('', exc_info=True)
                ## return -1

            delete_files(dst, self._logger)
            file_count += copy_files(src, dst_path, self._logger)
        return file_count

    def copy_tree(self, source, dest, exclude=[]):
        import os.path
        import shutil

        mode = self._options['mode']
        if mode == 'install':
            src = dest
            dst = source
        else:
            src = source
            dst = dest
        for root, dirs, files in os.walk(src):
            for dire in exclude:
                if dire in dirs:
                    dirs.remove(dire)
            if not os.path.exists(dst):
                os.makedirs(dst)
            for thefile in files:
                shutil.copy2(os.path.join(root, thefile), dst)

    def zip_tree(self, source, dest, name, exclude=[]):
        import os.path
        import zipfile

        mode = self._options['mode']
        if mode == 'install':
            src = dest
            dst = source
        else:
            src = source
            dst = dest
        with zipfile.ZipFile(name) as dstzip:
            for root, dirs, files in os.walk(src):
                for dire in exclude:
                    if dire in dirs:
                        dirs.remove(dire)
                if not os.path.exists(dst):
                    os.makedirs(dst)
                for thefile in files:
                    dstzip.write(os.path.join(root, thefile))

    def _requires_update(self, backup_dst, build_number):
        #import socket
        try:
            c = open(join(backup_dst, build_number, 'backup.id')).read().rstrip('\n')
            m = open(join(backup_dst, self._parse_env(self._options['backup_info']))).read().rstrip('\n')
            return c != m
        except IOError:
            self._logger.info('No update check file.')
            return True
        except:
            self._logger.error('Error checking for updates.', exc_info=True)
        return True

    def _check_for_valid_updates(self, versions=None):
        self._logger.debug('Checking for valid updates.')
        backup_dst = self._options['repo']
        valid = []
        if versions is None:
            versions = [self._env['$version']]

        for v in versions:
            self._env['$version'] = v
            for o in self._plugin_list:
                if not o in self._options['installs'] and not self._options['all_nodes']:
                    continue

                self._env['$node'] = o
                self._env['$backup'] = self._options['repo']

                if 'env' in self._plugin_list[o]:
                    if not self._update_env(self._plugin_list[o]['env']):
                        continue

                if 'valid_versions' in self._plugin_list[o]:
                    if not int(v) in [int(i) for i in self._plugin_list[o]['valid_versions']]:
                        continue

                if 'id_file' in self._plugin_list[o]:
                    self._options['backup_info'] = self._plugin_list[o]['id_file']
                build_number = self._parse_env(self._plugin_list[o]['destination'])
                if self._requires_update(backup_dst, build_number):
                    valid.append(o)
                if 'out' in self._plugin_list[o]:
                    for o in self._plugin_list[o]['out']:
                        out_file = join(backup_dst, self._parse_env(o[0]).lower())
                        try:
                            os.makedirs(os.path.dirname(out_file))
                        except:
                            pass  # self._logger.error('Error in make dir.', exc_info=True)
                        if os.path.exists(out_file):
                            out_version = open(out_file).read(-1).rstrip('\n')
                        else:
                            out_version = ''
                        current_version = self._parse_env(o[1])
                        if out_version != current_version:
                            with file(out_file, 'w') as f:
                                f.write(current_version)

        return valid

    def _process_versions(self, nodes_required):
        completed = False
        for v in self._options['versions']:
            self._env['$version'] = v
            completed &= self._process(v, nodes_required)
        return completed

    def _process_killer(self, processes_to_kill=None):
        self._logger.info('Starting process monitor.')
        if processes_to_kill is None:
            processes_to_kill = self._options['processes']
        import win32com.client
        while self._monitor_processes:
            try:
                wmi = win32com.client.GetObject('winmgmts:')
                for p in wmi.InstancesOf('win32_process'):
                    if p.name in processes_to_kill:
                        p.Terminate()
                # for p in psutil.process_iter():
                #     try:
                #         if p.name() in processes_to_kill:
                #             p.kill()
                #     except:
                #         self._logger.log(1, 'Access denied to exec.', exc_info=True)
                #         pass
            except:
                self._logger.error('Error in process killer.', exc_info=True)
            time.sleep(.5)
        self._logger.info('Stopping process monitor.')

    def _process(self, version=None, nodes_required=[]):
        if self._plugin_list is None:
            return
        fake = False
        completed = False
        self._logger.debug('Starting update process.')
        mode = self._options['mode']
        backup_dst = self._options['repo']

        for o in self._plugin_list:
            if not o in nodes_required:
                continue
            #if not o in self._options['installs'] and not self._options['all_nodes']:
            #    continue

            self._env['$node'] = o
            node = self._plugin_list[o]

            if 'valid_versions' in node:
                if not int(version) in [int(i) for i in node['valid_versions']]:
                    self._logger.info(
                        'Version %s not defined for this update node %s(%s).' % (version, o, node['valid_versions']))
                    continue

            node_env = None
            if 'env' in node:
                node_env = node['env']
                if not self._update_env(node_env):
                    continue

            if 'id_file' in node:
                self._options['backup_info'] = node['id_file']

            abort_failed = False
            if 'abort_failed' in node:
                abort_failed = node['abort_failed']

            base_dir = self._parse_env(node['basedir'])
            build_number = self._parse_env(node['destination'])
            file_count = 0
            self._logger.info("Processing '{0}' in {1} mode.".format(self._parse_env(node['name']), mode))

            if not self._requires_update(backup_dst, build_number) and mode != 'backup':
                self._logger.info('No updates required.')
                completed = True
                continue

            services = node['services'] if 'services' in node else {}
            processes = node['kill_processes'] if 'kill_processes' in node else []
            self._logger.info("Checking running processes %s." % processes)
            if self._is_process_running(processes, services):
                self._logger.info('Process running cannot update.')
                completed = False
                continue

            self._logger.debug("Root '{0}'".format(base_dir))
            self._logger.debug("Destination '{0}'".format(backup_dst))

            service_running = []
            for k in services.iterkeys():
                try:
                    self._logger.info('%s service stopping...' % k)
                    win32serviceutil.StopService(k)
                    service_running.append(k)
                    time.sleep(2)
                except:
                    self._logger.debug('Error stopping %s.' % k, exc_info=True)

            killer = None
            if len(processes) > 0:
                killer = threading.Thread(target=self._process_killer, kwargs={'processes_to_kill': processes})
                self._monitor_processes = True
                killer.start()

            if 'files' in node and not fake:
                files = node['files']
                # TODO: Restore files on failure
                file_count = self.copy_files(backup_dst, base_dir, build_number, files)
                if file_count == -1 and abort_failed:
                    self._logger.error('File copy failed. Aborting update.')
                    return False
            elif 'file-group' in node and not fake:
                file_group = node['file-group']
                for k, v in file_group.iteritems():
                    if not isinstance(v, list):
                        temp_basedir = self._parse_env(v)
                        group_destination = '%s_destination' % k
                        group_files = '%s_files' % k
                        group_dirs = '%s_dirs' % k
                        temp_destination = backup_dst

                        if group_destination in file_group:
                            temp_destination = join(self._options['repo'],
                                                    self._parse_env(file_group[group_destination]))

                        if group_files in file_group and isinstance(file_group[group_files], list):
                            self._logger.info('Processing file group %s' % k)
                            tmp_files = file_group[group_files]
                            self._logger.info('Copying file group %s.' % k)
                            file_count += self.copy_files(temp_destination, temp_basedir, build_number, tmp_files)
                        if group_dirs in file_group and isinstance(file_group[group_dirs], list):
                            self._logger.info('Processing file group %s' % k)
                            temp_dirs = file_group[group_dirs]
                            for d in temp_dirs:
                                b1 = os.path.dirname(os.path.join(temp_basedir, d))
                                d1 = os.path.dirname(os.path.join(temp_destination, d))
                                self._logger.info('Copying directory %s to %s' % (b1, d1))
                                self.copy_tree(b1, d1)
            elif 'ini' in node and not fake:
                ini = node['ini']
                section = self._parse_env(ini['section'])
                c = ConfigParser()
                c.optionxform = str
                root = None
                if mode == 'backup':
                    root = self._env['$maxroot']
                    self._env['$maxroot'] = join(backup_dst, build_number)
                c.read(self._parse_env(ini['file']))
                dirty = False
                if DONT_USE_PROGRESS:
                    it = ini['values']
                else:
                    it = progress.bar(ini['values'])
                for p in it:
                    action = p[0]
                    key = p[1]
                    if action == 'add':
                        v = p[2]
                        try:
                            v = c.get(section, key)
                        except (NoOptionError, NoSectionError):
                            if not c.has_section(section):
                                c.add_section(section)
                        if mode == 'install':
                            self._logger.info('Adding %s to ini section %s with value %s' % (key, section, v))
                            c.set(section, key, self._parse_env(v))
                        else:
                            c.set(section, key, v)
                        dirty = True
                    if action == 'del':
                        if c.has_option(section, key):
                            self._logger.info('Removing %s from ini section %s' % (key, section))
                            c.remove_option(section, key)
                if dirty:
                    try:
                        os.makedirs(dirname(self._parse_env(ini['file'])))
                    except WindowsError:
                        pass

                    with open(self._parse_env(ini['file']), mode='w') as f:
                        c.write(f)
                if mode == 'backup':
                    self._env['$maxroot'] = root
            elif 'out' in node and not fake:
                for o in node['out']:
                    try:
                        os.makedirs(dirname(os.path.dirname(o)))
                    except:
                        pass
                    with file(join(backup_dst, self._parse_env(o[0]).lower()), 'w') as f:
                        f.write(self._parse_env(o[1]))

            if mode == 'backup':
                #import uuid
                self._logger.debug('Building sha hash')
                id = GetHashofDirs(join(backup_dst, build_number))
                try:
                    os.makedirs(dirname(os.path.dirname(join(backup_dst, build_number, 'backup.id'))))
                except:
                    pass
                with file(join(backup_dst, build_number, 'backup.id'), 'w') as f:
                    f.write(id)

            r = open(join(backup_dst, build_number, 'backup.id')).read().rstrip('\n')
            with file(join(backup_dst, self._parse_env(self._options['backup_info'])), 'w') as f:
                f.write(r)

            self._logger.debug('\nCopied {0} files(s).'.format(file_count))

            if len(processes) > 0:
                self._monitor_processes = False
                killer.join()

            for k in service_running:
                try:
                    self._logger.info('%s service starting...' % k)
                    win32serviceutil.StartService(k)
                except:
                    self._logger.error('Error starting %s.' % k, exc_info=True)
            completed = True
        return completed