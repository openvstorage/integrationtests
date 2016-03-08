# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A general class dedicated to general logic
"""

import os
import grp
import pwd
import sys
import shutil
import logging
import subprocess
import ConfigParser
from ci.scripts import debug
from nose.plugins.skip import SkipTest
from ovs.extensions.generic.remote import Remote
from ovs.extensions.generic.sshclient import SSHClient


class General(object):
    """
    A general class dedicated to general logic
    """
    AUTOTEST_DIR = os.path.join(os.sep, "opt", "OpenvStorage", "ci")
    CONFIG_DIR = os.path.join(AUTOTEST_DIR, "config")
    TESTS_DIR = os.path.join(AUTOTEST_DIR, "tests")

    AUTOTEST_CFG_FILE = os.path.join(CONFIG_DIR, "autotest.cfg")
    OS_MAPPING_CFG_FILE = os.path.join(CONFIG_DIR, "os_mapping.cfg")

    logging.getLogger("paramiko").setLevel(logging.WARNING)

    if not hasattr(sys, "debugEnabled"):
        sys.debugEnabled = True
        debug.listen()

    @staticmethod
    def get_config():
        """
        Get autotest config
        """
        autotest_config = ConfigParser.ConfigParser()
        autotest_config.read(General.AUTOTEST_CFG_FILE)
        return autotest_config

    @staticmethod
    def save_config(config):
        """
        Save autotest config file
        :param config: Configuration to save
        """
        with open(General.AUTOTEST_CFG_FILE, "wb") as autotest_config:
            config.write(autotest_config)

    @staticmethod
    def execute_command(command, wait=True, shell=True):
        """
        Execute a command on local node
        :param command: Command to execute
        :param wait: Wait for command to finish
        :param shell: Use shell
        :return: Output, error code
        """
        child_process = subprocess.Popen(command,
                                         shell=shell,
                                         stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)

        if not wait:
            return child_process.pid
        (out, error) = child_process.communicate()
        return out, error

    @staticmethod
    def execute_command_on_node(host, command, password=None):
        """
        Execute a command on a specific host
        :param host: Host to execute command on
        :param command: Command to execute
        :param password: Password used to login on host
        :return: Output of command
        """
        cl = SSHClient(host, username='root', password=password)
        return cl.run(command)

    @staticmethod
    def check_file_is_link(file_path, host, username=None, password=None):
        """
        Check if a file on a node is a symlink
        :param host: Host node to check file system
        :param file_path: File to check eg. '/dev/disk/by-id/wwn-0x500003941b780823'
        :param password: Password used to login on host
        :return: Boolean
        """
        if username is None:
            username = 'root'
        with Remote(host, [os], username=username, password=password, strict_host_key_checking=False) as remote:
            return remote.os.path.islink(file_path)

    @staticmethod
    def check_prereqs(testcase_number, tests_to_run):
        """
        Check which test needs to run
        :param testcase_number: Number of testcase --> Used to determine if test needs to be executed
        :type testcase_number:  Integer

        :param tests_to_run:    Number(s) of tests of a testsuite to execute
        :type tests_to_run:     List

        :return: None
        """
        if 0 not in tests_to_run and testcase_number not in tests_to_run:
            raise SkipTest('Test number {0} not in the list of running tests.'.format(testcase_number))

    @staticmethod
    def cleanup():
        """
        Do some cleanup actions
        :return: None
        """
        from ci.tests.general.general_pmachine import GeneralPMachine
        from ci.tests.general.general_vdisk import GeneralVDisk
        from ci.tests.general.general_vmachine import GeneralVMachine

        def _get_remote_ssh_connection(ip_address, username, password):
            import paramiko
            ssh_connection = paramiko.SSHClient()
            ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_connection.connect(ip_address, username=username, password=password, timeout=2)
            sftp = ssh_connection.open_sftp()
            return ssh_connection, sftp

        # @TODO: Split this cleanup function up in relevant parts and put them in the correct general files
        machine_name = "AT_"

        from ci.tests.general import general_hypervisor
        from ci.tests.general.general_vpool import GeneralVPool
        for vpool in GeneralVPool.get_vpools():
            if vpool:
                hpv = general_hypervisor.Hypervisor.get(vpool)
                vm_names = [vm.name for vm in GeneralVMachine.get_vmachines()]
                for name in vm_names:
                    vm = GeneralVMachine.get_vmachine_by_name(name)
                    if not vm:
                        continue
                    vm = vm[0]
                    if not vm.name.startswith(machine_name):
                        continue
                    if vm.is_vtemplate:
                        hpv.delete_clones(vm)
                    logging.log(1, "Deleting {0} on hypervisor".format(vm.name))
                    hpv.poweroff(vm.name)
                    hpv.delete(vm.name)

                env_macs = General.execute_command("""ip a | awk '/link\/ether/ {gsub(":","",$2);print $2;}'""")[0].splitlines()
                if vpool.storagedrivers:
                    mountpoint = vpool.storagedrivers[0].mountpoint
                    if os.path.exists(mountpoint):
                        for d in os.listdir(mountpoint):
                            if d.startswith(machine_name):
                                p = os.path.join(mountpoint, d)
                                if os.path.isdir(p):
                                    logging.log(1, "removing tree: {0}".format(p))
                                    shutil.rmtree(p)
                                else:
                                    logging.log(1, "removing file: {0}".format(p))
                                    if os.path.isfile(p):
                                        os.remove(p)
                        for mac in env_macs:
                            mac_path = os.path.join(mountpoint, mac)
                            if os.path.exists(mac_path):
                                for f in os.listdir(mac_path):
                                    logging.log(1, "removing file: {0}".format(f))
                                    os.remove(os.path.join(mac_path, f))

                # remove existing disks
                vdisks = GeneralVDisk.get_vdisks()
                for vdisk in vdisks:
                    if vdisk:
                        for junction in vdisk.mds_services:
                            if junction:
                                junction.delete()
                        vdisk.delete()
                        logging.log(1, 'WARNING: Removed leftover disk: {0}'.format(vdisk.name))

                GeneralVPool.remove_vpool(vpool)

                if GeneralPMachine.get_hypervisor_type() == 'VMWARE':
                    from ci.tests.general.general_hypervisor import GeneralHypervisor
                    hypervisor_info = GeneralHypervisor.get_hypervisor_info()
                    ssh_con = _get_remote_ssh_connection(*hypervisor_info)[0]
                    cmd = "esxcli storage nfs remove -v {0}".format(vpool.name)
                    ssh_con.exec_command(cmd)

                vmachines = GeneralVMachine.get_vmachines()
                for vmachine in vmachines:
                    logging.log(1, 'WARNING: Removing leftover vmachine: {0}'.format(vmachine.name))
                    vmachine.delete()

    @staticmethod
    def get_loop_devices(client):
        """
        Retrieve all loop devices
        :param client: SSHClient object
        :return: Loop device information
        """
        return [entry.split()[0] for entry in client.run('lsblk').splitlines() if 'loop' in entry]

    @staticmethod
    def get_mountpoints(client):
        """
        Retrieve the mountpoints on the specified client
        :param client: SSHClient object
        :return: List of mountpoints
        """
        mountpoints = []
        for mountpoint in client.run('mount -v').strip().splitlines():
            mp = mountpoint.split(' ')[2] if len(mountpoint.split(' ')) > 2 else None
            if mp and not mp.startswith('/dev') and not mp.startswith('/proc') and not mp.startswith('/sys') and not mp.startswith('/run') and not mp.startswith('/mnt/alba-asd') and mp != '/':
                mountpoints.append(mp)
        return mountpoints

    @staticmethod
    def list_os():
        """
        List os' configured in os_mapping
        """
        os_mapping_config = ConfigParser.ConfigParser()
        os_mapping_config.read(General.OS_MAPPING_CFG_FILE)
        return os_mapping_config.sections()

    @staticmethod
    def get_os_info(os_name):
        """
        Get info about an os configured in os_mapping
        :param os_name: Name of operating system to retrieve information for
        """
        os_mapping_config = ConfigParser.ConfigParser()
        os_mapping_config.read(General.OS_MAPPING_CFG_FILE)

        if not os_mapping_config.has_section(os_name):
            print("No configuration found for os {0} in config".format(os_name))
            return

        return dict(os_mapping_config.items(os_name))

    @staticmethod
    def set_os(os_name):
        """
        Set current os to be used by tests
        :param os_name: Name of operating system to set
        """
        os_list = General.list_os()
        if os_name not in os_list:
            print("Invalid os specified, available options are {0}".format(str(os_list)))
            return False

        config = General.get_config()
        config.set(section="main", option="os", value=os_name)
        General.save_config(config)
        return True

    @staticmethod
    def get_os():
        """
        Retrieve current configured os for autotests
        """
        return General.get_config().get(section="main", option="os")

    @staticmethod
    def set_template_server(template_server):
        """
        Set current template server to be used by tests
        :param template_server: Template server to set
        """

        config = General.get_config()
        config.set(section="main", option="template_server", value=template_server)
        General.save_config(config)
        return True

    @staticmethod
    def get_template_server():
        """
        Retrieve current configured template server for autotests
        """
        return General.get_config().get(section="main", option="template_server")

    @staticmethod
    def get_username():
        """
        Get username to use in tests
        """
        return General.get_config().get(section="main", option="username")

    @staticmethod
    def set_username(username):
        """
        Set username to use in tests
        :param username: Username to set
        """
        config = General.get_config()
        config.set(section="main", option="username", value=username)
        General.save_config(config)
        return True

    @staticmethod
    def get_password():
        """
        Get password to use in tests
        """
        return General.get_config().get(section="main", option="username")

    @staticmethod
    def set_password(password):
        """
        Set password to use in tests
        :param password: Password to set
        """
        config = General.get_config()
        config.set(section="main", option="password", value=password)
        General.save_config(config)
        return True

    @staticmethod
    def filter_files(files, extensions, exclude_dirs=None, include_dirs=None, exclude_files=None, include_files=None):
        """
        Recursively get all files in root_folder
        :param files: Files to filter
        :param extensions: File extensions to add to the filter
        :param exclude_dirs: Files to exclude from filter
        :param include_dirs: Files to include in filter
        :param exclude_files: Files to exclude even though they match extensions and/or are part of include_dirs
        :param include_files: Files to include even though they don't match extensions and/or are part of exclude_dirs
        :return: List of files
        """
        filtered_files = []
        for file_name in files:
            # Verify include files
            if file_name in include_files:
                filtered_files.append(file_name)
                continue

            # Verify exclude files
            if file_name in exclude_files:
                continue

            # Verify extension
            valid_extension = False
            for extension in extensions:
                if file_name.endswith(extension):
                    valid_extension = True
                    break
            if valid_extension is False:
                continue

            # Verify include directories
            file_included = False
            for include_dir in include_dirs:
                if file_name.startswith(include_dir):
                    filtered_files.append(file_name)
                    file_included = True
                    break
            if file_included is True:
                continue

            # Verify exclude directories
            file_excluded = False
            for exclude_dir in exclude_dirs:
                if file_name.startswith(exclude_dir):
                    file_excluded = True
                    break
            if file_excluded is True:
                continue

            filtered_files.append(file_name)
        return filtered_files

    @staticmethod
    def get_owner_group_for_path(path, root_client=None):
        """
        Retrieve the owner and group name for the specified path
        :param path: Path to retrieve information about
        :param root_client: SSHClient object
        :return: Owner and group information
        """
        if root_client is None:
            root_client = SSHClient(endpoint='127.0.0.1', username='root')
        if not root_client.file_exists(filename=path) and not root_client.dir_exists(directory=path):
            raise ValueError('The specified path is not a file nor a directory')

        stat_info = os.stat(path)
        uid = stat_info.st_uid
        gid = stat_info.st_gid

        user = pwd.getpwuid(uid)[0]
        group = grp.getgrgid(gid)[0]

        return {'user': {'id': uid,
                         'name': user},
                'group': {'id': gid,
                          'name': group}}
