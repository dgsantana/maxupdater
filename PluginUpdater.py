#!/usr/bin/python2.7
from argparse import ArgumentParser
from collections import OrderedDict
import os
import sys
from os import makedirs
from os.path import join, dirname
import _winreg
import logging
from ConfigParser import NoOptionError, NoSectionError, ConfigParser

import yaml

from dsutils import copy_files, delete_files, GetHashofDirs
from sys import exc_info
#from examples.smbcat import file

try:
    from clint.textui import progress
except ImportError:
    pass

if "progress" in dir():
    DONT_USE_PROGRESS = False
else:
    DONT_USE_PROGRESS = True


def foo_callback(option, opt, value, parser):
    setattr(parser.values, option.dest, value.split(','))


class PluginUpdater(object):
    """description of class"""

    def __init__(self):
        parser = ArgumentParser()
        parser.add_argument('-m', '--mode', dest="mode", default="backup", choices=['install', 'backup'],
                            help='interaction mode: install, backup')
        parser.add_argument('-i', '--install', dest="mode", action="store_const", const="install",
                            help='install mode')
        parser.add_argument('-v', '--maxversion', dest="max_version", default="0",
                            help='3ds max version number')
        parser.add_argument('-s', '--sourcemaxversion', dest="source_version", default=None,
                            help='source 3ds max version number')
        parser.add_argument('-d', '--debug', dest="verbose", action="store_true",
                            help='verbose mode')
        parser.add_argument('-q', '--quiet', dest="verbose", action="store_false",
                            help='quiet mode')
        parser.add_argument('-p', '--path', dest="path", default="\\\\4arq-server00\\NetInstall\\max_plugs\\",
                            help='backup path')
        parser.add_argument('-n', '--node', dest="node", default='maxplugins',
                            help='node do backup/install')
        parser.add_argument('-a', '--all', dest="allnodes", default=False,
                            help='copy all nodes')

        options = parser.parse_args()
        self._options = options
        self._yaml = {}
        import socket

        self._env = {'$version': self._options.max_version, '$host': socket.gethostname().lower()}
        self._backup_info = '$host_$node.id'
        self._dirtyFile = True
        self._notify = None
        self.options_node = self._options.node
        self._logger = logging.getLogger('MaxUpdater')

    def load_updater_info(self):
        f = join(self._options.path, 'plugins.yaml')
        if os.path.exists(f):
            m = os.path.getmtime(f)
            if self._notify != m:
                self._notify = m
            else:
                return
            self._logger.info('Loading updater info.')
            self._yaml = yaml.load(open(f))
            self._dirtyFile = False

    def _set_env(self, env_key):
        for k, v in env_key.iteritems():
            if v[0] == 'setenv':
                name = self.parse_env(v[1])
                value = self.parse_env(v[2])
                path = r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
                reg = _winreg.ConnectRegistry(None, _winreg.HKEY_LOCAL_MACHINE)
                key = _winreg.OpenKey(reg, path, 0, _winreg.KEY_ALL_ACCESS)
                _winreg.SetValueEx(key, name, 0, _winreg.REG_EXPAND_SZ, value)
                self._logger.info('Setting env: %s=%s' % (name, value))
            elif v[0] == 'setreg':
                path = self.parse_env(v[1])
                name = self.parse_env(v[2])
                value = self.parse_env(v[3])
                self._set_reg(path, name, value)
                self._logger.info('Setting Registry: %s[%s]=%s' % (path, name, value))

    def update_env(self, d):
        """
        @type d: dict
        @param d:
        @return:
        """
        result = True
        for k, v in d.iteritems():
            if v[0] == 'reg':
                self._env[k] = self.get_reg(self.parse_env(v[1]), self.parse_env(v[2]))
                if self._env[k] is None:
                    result = False
                else:
                    self._logger.debug("Adding env['%s'] = '%s'" % (k, self._env[k]))
        return result

    def get_reg(self, hkey, query):
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

    def _set_reg(self, hkey, query, value):
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

    def parse_env(self, s):
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
        mode = self._options.mode
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
                makedirs(dirname(dst))
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

        mode = self._options.mode
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
        import shutil
        import zipfile

        mode = self._options.mode
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

    def requires_update(self, backup_dst, build_number):
        #import socket
        try:
            c = open(join(backup_dst, build_number, 'backup.id')).read().rstrip('\n')
            #n1 = '%(host)s_%(node)s.id' % {'host': self._env['$host'], 'node': build_number}
            m = open(join(backup_dst, self.parse_env(self._backup_info))).read().rstrip('\n')
            return c != m
        except:
            pass
        return True

    def check_for_valid_updates(self, versions=None):
        backup_dst = self._options.path
        valid = False
        if versions is None:
            versions = [self._env['$version']]

        for v in versions:
            self._env['$version'] = v
            for o in self._yaml:
                if not o in self.options_node and not self._options.allnodes:
                    continue

                self._env['$node'] = o
                self._env['$backup'] = self._options.path

                if 'env' in self._yaml[o]:
                    if not self.update_env(self._yaml[o]['env']):
                        continue

                if 'id_file' in self._yaml[o]:
                    self._backup_info = self._yaml[o]['id_file']
                build_number = self.parse_env(self._yaml[o]['destination'])
                if self.requires_update(backup_dst, build_number):
                    valid = True

        return valid

    def process_versions(self, versions):
        for v in versions:
            self._env['$version'] = v
            self.process()

    def process(self, fake=False):
        if self._yaml is None:
            return
        mode = self._options.mode
        backup_dst = self._options.path

        for o in self._yaml:
            if not o in self.options_node and not self._options.allnodes:
                continue

            self._env['$node'] = o

            node = self._yaml[o]
            node_env = None
            if 'env' in node:
                node_env = node['env']
                if not self.update_env(node_env):
                    continue

            if 'id_file' in node:
                self._backup_info = node['id_file']

            abort_failed = False
            if 'abort_failed' in node:
                abort_failed = node['abort_failed']

            if 'valid_versions' in node:
                if not int(self._env['$version']) in [int(i) for i in node['valid_versions']]:
                    self._logger.info(
                        'Version %s not defined for this update node %s(%s).' % (
                            self._env['$version'], o, node['valid_versions']))
                    continue

            base_dir = self.parse_env(node['basedir'])
            build_number = self.parse_env(node['destination'])
            file_count = 0
            self._logger.info("Processing '{0}' in {1} mode.".format(self.parse_env(node['name']), mode))
            self._logger.debug("Root '{0}'".format(base_dir))
            self._logger.debug("Destination '{0}'".format(backup_dst))
            if not self.requires_update(backup_dst, build_number) and mode != 'backup':
                self._logger.debug('No update required.')
                continue

            # Rename core file to prevent running while updating
            # Renaming 3dsmax.exe can break shortcuts.
            process_protect = []
            if mode == 'install':
                if 'tmp' in node and not fake:
                    process_protect = node['tmp']
                    if len(process_protect) == 2:
                        try:
                            os.rename(join(base_dir, process_protect[0]), join(base_dir, process_protect[1]))
                        except:
                            self._logger.error('File not found {0}.'.format(process_protect[0]))

            if 'files' in node and not fake:
                files = node['files']
                # TODO: Restore files on failure
                file_count = self.copy_files(backup_dst, base_dir, build_number, files)
                if file_count == -1 and abort_failed:
                    self._logger.error('File copy failed. Aborting update.')
                    return False

            if 'file-group' in node and not fake:
                file_group = node['file-group']
                for k, v in file_group.iteritems():
                    if not isinstance(v, list):
                        temp_basedir = self.parse_env(v)
                        group_destination = '%s_destination' % k
                        group_files = '%s_files' % k
                        group_dirs = '%s_dirs' % k
                        temp_destination = backup_dst

                        if group_destination in file_group:
                            temp_destination = join(self._options.path, self.parse_env(file_group[group_destination]))

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

            if 'ini' in node and not fake:
                ini = node['ini']
                section = self.parse_env(ini['section'])
                c = ConfigParser()
                c.optionxform = str
                if mode == 'backup':
                    root = self._env['$maxroot']
                    self._env['$maxroot'] = join(backup_dst, build_number)
                c.read(self.parse_env(ini['file']))
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
                            c.set(section, key, self.parse_env(v))
                        else:
                            c.set(section, key, v)
                        dirty = True
                    if action == 'del':
                        if c.has_option(section, key):
                            self._logger.info('Removing %s from ini section %s' % (key, section))
                            c.remove_option(section, key)
                if dirty:
                    try:
                        makedirs(dirname(self.parse_env(ini['file'])))
                    except WindowsError:
                        pass

                    with open(self.parse_env(ini['file']), mode='w') as f:
                        c.write(f)
                if mode == 'backup':
                    self._env['$maxroot'] = root

            if mode == 'backup':
                import socket
                #import uuid
                self._logger.debug('Building sha hash')
                id = GetHashofDirs(join(backup_dst, build_number))  #uuid.uuid4().get_hex()
                with file(join(backup_dst, build_number, 'backup.id'), 'w') as f:
                    f.write(id)
            r = open(join(backup_dst, build_number, 'backup.id')).read().rstrip('\n')
            with file(join(backup_dst, self.parse_env(self._backup_info)), 'w') as f:
                f.write(r)

            if 'out' in node and not fake:
                for o in node['out']:
                    with file(join(backup_dst, self.parse_env(o[0]).lower()), 'w') as f:
                        f.write(self.parse_env(o[1]))

            # Rename core file to prevent running while updating - Restore
            if mode == 'install':
                if len(process_protect) == 2:
                    try:
                        os.rename(join(base_dir, process_protect[1]), join(base_dir, process_protect[0]))
                    except:
                        self._logger.error('File not found {0}.'.format(process_protect[1]))
                if node_env and not fake:
                    self._set_env(node_env)

            self._logger.debug('\nCopied {0} files(s).'.format(file_count))


if __name__ == '__main__':
    print("Plugin Installer/Backup v1.5")
    plug = PluginUpdater()
    plug._logger.addHandler(logging.StreamHandler())
    plug._logger.setLevel(logging.DEBUG)
    plug.load_updater_info()
    plug.process()
