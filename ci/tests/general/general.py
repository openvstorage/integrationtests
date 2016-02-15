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


import datetime
import inspect
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import time
sys.path.append(os.path.join(os.sep, "opt", "OpenvStorage", "ci", "scripts"))
from nose.plugins.skip import SkipTest
from ovs.dal.lists.backendlist import BackendList
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.dal.lists.vdisklist import VDiskList
from ovs.dal.lists.vmachinelist import VMachineList
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System
from ovs.lib.setup import SetupController
from ovs.lib.storagerouter import StorageRouterController
import general_hypervisor
from ci import autotests
import debug
import paramiko

if not hasattr(sys, "debugEnabled"):
    sys.debugEnabled = True
    debug.listen()

logging.getLogger("paramiko").setLevel(logging.WARNING)

test_config = autotests.get_config()
current_test = None    # Used by each individual test to indicate which test is running and is used by 'take_screenshot'
screenshot_dir = None  # Used by each testsuite to indicate which testsuite is running and is used by 'take_screenshot'


def execute_command(command, wait=True, shell=True):
    child_process = subprocess.Popen(command,
                                     shell=shell,
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)

    if not wait:
        return child_process.pid
    (out, error) = child_process.communicate()
    return out, error


def execute_command_on_node(host, command, password=None):
    cl = SSHClient(host, username='root', password=password)
    return cl.run(command)


def get_elem_with_val(iterable, key, value):
    """
    iterable : Iterable of dict items
    """
    return [e for e in iterable if e.get(key, "iNvAlId_VaLuE") == value]


def get_line_number():
    """Returns the current line number in our program."""
    return inspect.currentframe().f_back.f_lineno


def check_prereqs(testcase_number, tests_to_run):
    """
    Check which test needs to run
    @param testcase_number:    Number of testcase --> Used to determine if test needs to be executed
    @type testcase_number:     Integer

    @param tests_to_run:       Number(s) of tests of a testsuite to execute
    @type tests_to_run:        List of Integers

    @return:                  None
    """
    if 0 not in tests_to_run and testcase_number not in tests_to_run:
        raise SkipTest()


def get_tests_to_run(test_level):
    """
    Retrieves the tests to be executed in the testsuite (from autotest config file)

    @return: List of numbers of tests to be executed
    """

    tests = test_level
    tests_to_run = []
    if tests:
        for number in tests.split(','):
            if not number.find('-') >= 0:
                tests_to_run.append(int(number))
            else:
                numbers = number.split('-')
                if int(numbers[0]) > int(numbers[1]):
                    swap_number = numbers[0]
                    numbers[0] = numbers[1]
                    numbers[1] = swap_number

                tests_to_run.append(int(numbers[0]))
                for k in range(int(numbers[0]) + 1, int(numbers[1]) + 1):
                    tests_to_run.append(k)

    return sorted(list(set(tests_to_run)))


def get_remote_ssh_connection(ip_address, username, password):
    """
    """
    ssh_connection = paramiko.SSHClient()
    ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_connection.connect(ip_address, username=username, password=password, timeout=2)
    sftp = ssh_connection.open_sftp()
    return ssh_connection, sftp


def get_ip_for(hostname):
    cmd = "cat /etc/hosts | awk '/{0}/".format(hostname) + " {print $1}'"
    ips = execute_command(cmd)[0].splitlines()
    for ip in ips:
        if ip == '127.0.0.1':
            continue
        return ip


def get_virbr_ip():
    ip = execute_command("ip a | awk '/inet/ && /virbr0/ {print $2}'")[0].strip()
    return ip


def get_local_vsa():
    local_ip_info = execute_command("ip a")[0]
    for vsa in StorageRouterList.get_storagerouters():
        if vsa.ip in local_ip_info:
            return vsa


def get_function_name(level=0):
    """
    Returns the functionName of the test being executed currently

    @param level: Depth of path returned
    @type level:  Integer

    @return:      Name of the test
    """
    return sys._getframe(level + 1).f_code.co_name


def cleanup():
    machine_name = "AT_"

    for vpool in VPoolList.get_vpools():
        if vpool:
            hpv = general_hypervisor.Hypervisor.get(vpool.name, cleanup=True)
            vm_names = [vm.name for vm in VMachineList.get_vmachines()]
            for name in vm_names:
                vm = VMachineList.get_vmachine_by_name(name)
                if not vm:
                    continue
                vm = vm[0]
                if not vm.name.startswith(machine_name):
                    continue
                if vm.is_vtemplate:
                    hpv.delete_clones(vm.name)
                logging.log(1, "Deleting {0} on hypervisor".format(vm.name))
                hpv.poweroff(vm.name)
                hpv.delete(vm.name)

            env_macs = execute_command("""ip a | awk '/link\/ether/ {gsub(":","",$2);print $2;}'""")[0].splitlines()
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
            vdisks = VDiskList.get_vdisks()
            for vdisk in vdisks:
                if vdisk:
                    for junction in vdisk.mds_services:
                        if junction:
                            junction.delete()
                    vdisk.delete()
                    logging.log(1, 'WARNING: Removed leftover disk: {0}'.format(vdisk.name))

            api_remove_vpool(vpool.name)

            if general_hypervisor.get_hypervisor_type() == "VMWARE":
                hypervisor_info = autotests.get_hypervisor_info()
                ssh_con = get_remote_ssh_connection(*hypervisor_info)[0]
                cmd = "esxcli storage nfs remove -v {0}".format(vpool.name)
                ssh_con.exec_command(cmd)

            vmachines = VMachineList.get_vmachines()
            for vmachine in vmachines:
                logging.log(1, 'WARNING: Removing leftover vmachine: {0}'.format(vmachine.name))
                vmachine.delete()
    # remove_alba_namespaces()


def get_vpools():
    return VPoolList.get_vpools()


def add_vpool(browser):
    browser.add_vpool()

    if general_hypervisor.get_hypervisor_type() == "VMWARE":
        hypervisor_info = autotests.get_hypervisor_info()

        vpool_name = browser.vpool_name
        vpool = VPoolList.get_vpool_by_name(vpool_name)

        for sd in vpool.storagedrivers:
            hypervisor_info[0] = sd.storagerouter.pmachine.ip
            ssh_con = get_remote_ssh_connection(*hypervisor_info)[0]

            storage_ip = sd.storage_ip

            cmd = "esxcli storage nfs add -H {0} -s /mnt/{1} -v {1}".format(storage_ip, vpool_name)
            os.write(1, str(hypervisor_info) + "\n")
            os.write(1, cmd + "\n")
            _, stdout, stderr = ssh_con.exec_command(cmd)
            os.write(1, str(stdout.readlines()))
            os.write(1, str(stderr.readlines()))


def remove_vpool(browser):
    vpool_name = browser.vpool_name
    browser.remove_vpool(vpool_name)

    if general_hypervisor.get_hypervisor_type() == "VMWARE":
        hypervisor_info = autotests.get_hypervisor_info()
        ssh_con = get_remote_ssh_connection(*hypervisor_info)[0]

        _, stdout, _ = ssh_con.exec_command("esxcli storage nfs list")
        out = "\n".join(stdout.readlines())
        if vpool_name in out:

            cmd = "esxcli storage nfs remove -v {0}".format(vpool_name)
            stdin, stdout, stderr = ssh_con.exec_command(cmd)
            print stdout.readlines()
            print stderr.readlines()
    # remove_alba_namespaces()
    validate_vpool_cleanup(vpool_name)


def get_this_hostname():
    return execute_command("hostname")[0].strip()


def get_all_disks():
    out = execute_command("""fdisk -l 2>/dev/null| awk '/Disk \/.*:/ {gsub(":","",$s);print $2}'""")[0]
    return out.splitlines()


def get_unused_disks():
    all_disks = get_all_disks()
    out = execute_command("df -h | awk '{print $1}'")[0]

    unused_disks = [d for d in all_disks if d not in out and not execute_command("fuser {0}".format(d))[0]]

    return unused_disks


def get_disk_size(disk_path):
    fd = os.open(disk_path, os.O_RDONLY)
    size = os.lseek(fd, 0, os.SEEK_END)
    os.close(fd)
    return size


def get_disk_path_by_label(label):
    return execute_command("readlink /dev/disk/by-label/{0} -f".format(label))[0].strip()


def get_filesystem_size(mount_point):
    statvfs = os.statvfs(mount_point)
    full_size = statvfs.f_frsize * statvfs.f_blocks
    available_size = statvfs.f_bavail * statvfs.f_frsize
    used_size = (statvfs.f_blocks - statvfs.f_bfree) * statvfs.f_frsize
    nonroot_total = available_size + used_size

    return full_size, nonroot_total, available_size, used_size


def find_mount_point(path):
    path = os.path.abspath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def human2bytes(s):
    """
    Attempts to guess the string format based on default symbols
    set and return the corresponding bytes as an integer.
    When unable to recognize the format ValueError is raised.

      >>> human2bytes('0 B')
      0
      >>> human2bytes('1 K')
      1024
      >>> human2bytes('1 M')
      1048576
      >>> human2bytes('1 Gi')
      1073741824
      >>> human2bytes('1 tera')
      1099511627776

      >>> human2bytes('0.5kilo')
      512
      >>> human2bytes('0.1  byte')
      0
      >>> human2bytes('1 k')  # k is an alias for K
      1024
      >>> human2bytes('12 foo')
      Traceback (most recent call last):
          ...
      ValueError: can't interpret '12 foo'
    """
    symbols = {'customary': ('B', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y'),
               'customary_ext': ('byte', 'kilo', 'mega', 'giga', 'tera', 'peta', 'exa',
                                 'zetta', 'iotta'),
               'iec': ('Bi', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB'),
               'iec_ext': ('byte', 'kibi', 'mebi', 'gibi', 'tebi', 'pebi', 'exbi',
                           'zebi', 'yobi'),
               }

    init = s
    num = ""
    while s and s[0:1].isdigit() or s[0:1] == '.':
        num += s[0]
        s = s[1:]
    num = float(num)
    letter = s.strip()
    for name, units in symbols.items():
        if letter in units:
            break
    else:
        if letter == 'k':
            # treat 'k' as an alias for 'K' as per: http://goo.gl/kTQMs
            units = symbols['customary']
            letter = letter.upper()
        else:
            raise ValueError("can't interpret {0}".format(init))
    prefix = {units[0]: 1}
    for i, s in enumerate(units[1:]):
        prefix[s] = 1 << (i + 1) * 10
    return int(num * prefix[letter])


def api_add_vpool(vpool_name=None,
                  vpool_config='vpool',
                  vpool_type=None,
                  vpool_host=None,
                  vpool_port=None,
                  vpool_access_key=None,
                  vpool_secret_key=None,
                  vpool_storage_ip=None,
                  apply_to_all_nodes=True,
                  integratemgmt=True,
                  config_cinder=False,
                  backend_name=None,
                  vpool_config_params=None):

    local_vsa_ip = get_local_vsa().ip
    if vpool_config_params is None:
        vpool_config_params = {}

    if not vpool_name:
        vpool_name = test_config.get(vpool_config, 'vpool_name')

    if not backend_name:
        backend_name = test_config.get('backend', 'name')

    parameters = {'storagerouter_ip': local_vsa_ip,
                  'vpool_name': vpool_name,
                  'type': vpool_type or test_config.get(vpool_config, "vpool_type"),
                  'connection_host': vpool_host or test_config.get(vpool_config, "vpool_host"),
                  'connection_port': vpool_port or int(test_config.get(vpool_config, "vpool_port")),
                  'connection_username': vpool_access_key or test_config.get(vpool_config, "vpool_access_key"),
                  'connection_password': vpool_secret_key or test_config.get(vpool_config, "vpool_secret_key"),
                  'readcache_size': 50,
                  'writecache_size': 50,
                  'storage_ip': vpool_storage_ip or test_config.get(vpool_config, "vpool_storage_ip"),
                  'config_cinder': config_cinder,
                  'cinder_pass': "rooter",
                  'cinder_user': "admin",
                  'cinder_tenant': "admin",
                  'cinder_controller': local_vsa_ip,
                  'integratemgmt': integratemgmt,
                  'backend_name': backend_name,
                  'config_params': vpool_config_params or json.loads(test_config.get(vpool_config, "vpool_config_params"))
                  }

    if parameters['type'] == 'alba':
        alba_backend_guid = ''
        for backend in BackendList.get_backends():
            if backend.name.startswith(backend_name):
                alba_backend_guid = backend.alba_backend_guid
                break

        assert alba_backend_guid, "No backend of specified alba type found!"
        parameters['connection_backend'] = {'backend': alba_backend_guid, 'metadata': 'default'}

    print "Adding vpool: "
    print parameters

    if apply_to_all_nodes:
        storagerouters = [(sr.ip, sr.machine_id) for sr in StorageRouterList.get_storagerouters()]
        StorageRouterController.update_storagedrivers([], storagerouters, parameters)
    else:
        StorageRouterController.add_vpool(parameters)

    return parameters


def api_remove_vpool(vpool_name):
    mount_point = ''
    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        return

    for sd in vpool.storagedrivers:
        mount_point = sd.mountpoint
        storagerouter = sd.storagerouter
        storagerouter_machineid = storagerouter.machine_id
        local_machineid = System.get_my_machine_id()
        logging.log(1, "local_machine_id: {0}".format(local_machineid))
        logging.log(1, "storagerouter_machine_id: {0}".format(storagerouter_machineid))

        if local_machineid == storagerouter_machineid:
            # Inline execution, since it's on the same node (preventing deadlocks)
            StorageRouterController.remove_storagedriver(sd.guid)
        else:
            # Async execution, since it has to be executed on another node
            # @TODO: Will break in Celery 3.2, need to find another solution
            # Requirements:
            # - This code cannot continue until this new task is completed (as all these VSAs need to be
            # handled sequentially
            # - The wait() or get() method are not allowed anymore from within a task to prevent deadlocks
            result = StorageRouterController.remove_storagedriver.s(sd.guid).apply_async(
                routing_key='sr.{0}'.format(storagerouter_machineid)
            )
            result.wait()
        time.sleep(3)

    if mount_point:
        retries = 20
        while retries:
            if not os.path.exists(mount_point):
                break
            time.sleep(1)
            retries -= 1
        assert retries, "Mountpoint {0} of vpool still exists after removing storage driver".format(mount_point)


def apply_disk_layout(disk_layout):
    # @TODO: remove this when http://jira.cloudfounders.com/browse/OVS-1336 is fixed
    ovs_fstab_start = "BEGIN Open vStorage"
    execute_command("sed -i '/{0}/d' /etc/fstab".format(ovs_fstab_start))

    print "Disk layout to apply: {0}".format(disk_layout)

    grid_ip = test_config.get("main", "grid_ip")
    client = SSHClient(grid_ip, username='root', password='rooter')
    sc = SetupController()

    print "Fstab before apply_flexible_disk_layout\n", execute_command("cat /etc/fstab")[0]

    sc.apply_flexible_disk_layout(client, True, disk_layout)

    print "Fstab after apply_flexible_disk_layout\n", execute_command("cat /etc/fstab")[0]

    mounts = execute_command("df")[0].splitlines()
    print "\n".join(mounts)

    for mp, device in disk_layout.iteritems():
        device = device['device']
        mount = [m for m in mounts if device in m and mp in m]
        if device != "DIR_ONLY":
            assert mount, "{0}, device {1} was not mounted after apply_flexible_disk_layout\nDisk Layout: {2}".\
                format(mp, device, disk_layout)
        else:
            assert not mount, "DIR_ONLY {0} should not be mounted after apply_flexible_disk_layout\nDisk Layout: {1}".\
                format(mp, disk_layout)


def clean_disk_layout(disk_layout):
    if test_config.get("main", "cleanup") != "True":
        return
    print "df before clean\n", execute_command("df")[0]
    disks_to_clean = []
    for mp, device in disk_layout.iteritems():
        execute_command("umount {0}".format(mp))
        cmd = "sed -i '/{0}/d' /etc/fstab".format(mp.replace("/", "\/"))
        execute_command(cmd)
        try:
            os.removedirs(mp)
        except OSError:
            pass
        device_path = device['device']
        if device_path != "DIR_ONLY":
            disks_to_clean.append(device_path)

    for disk in set(disks_to_clean):
        cmd = 'parted {0} -s "mklabel gpt"'.format(disk)
        print cmd
        print execute_command(cmd)
    print "df after clean \n", execute_command("df")[0]


def validate_vpool_size_calculation(vpool_name, disk_layout, initial_part_used_space):
    """

    @param vpool_name:                  Name of vpool
    @type vpool_name:                   String

    @param disk_layout:                 Disk layout dict
    @type disk_layout:                  Dict

    @param initial_part_used_space:     Dict with used space for each partition at the beginning of test
    @type initial_part_used_space:      Dict

    @return:             None
    """

    with open("/opt/OpenvStorage/config/storagedriver/storagedriver/{0}.json".format(vpool_name)) as vpool_json_file:
        vpool_json = json.load(vpool_json_file)

    mount_points = vpool_json['content_addressed_cache']['clustercache_mount_points'] +\
        vpool_json['scocache']['scocache_mount_points']
    _temp_ = dict()
    _temp_['path'] = vpool_json['dtl']['dtl_path']
    _temp_['size'] = '0KiB'
    mount_points.append(_temp_)
    print "mount_points: {0}".format(mount_points)

    real_mount_points = [(mp['path'], find_mount_point(mp['path'])) for mp in mount_points]
    print "real_mount_points: {0}".format(real_mount_points)

    all_on_root = [find_mount_point(d) == "/" for d in disk_layout]
    print "all_on_root: {0}".format(all_on_root)

    reserved_on_root = 0

    for mp in mount_points:
        mp_path = os.path.dirname(mp['path'])
        dl = disk_layout[mp_path]
        dev_path = dl['device']
        print "mp_path: ", str(mp_path)
        print "mp: ", str(mp)
        print "dl: ", str(dl)
        if dev_path == 'DIR_ONLY':
            real_mount_point = find_mount_point(mp['path'])
            print 'real_mount_point: {0}'.format(real_mount_point)
            other_mount_point = [rm for rm in real_mount_points if rm[0] != mp['path'] and rm[1] == real_mount_point]
            print 'other_mount_point: {0}'.format(other_mount_point)
            if other_mount_point:
                if len(all_on_root) in [2, 3]:
                    if "sco" in mp['path']:
                        expected_reserved_percent = 20
                    else:
                        expected_reserved_percent = 49
                else:
                    expected_reserved_percent = 24
            else:
                expected_reserved_percent = 49
            mount_size = get_filesystem_size(real_mount_point)[1] - initial_part_used_space['/']
            reserved_on_root += expected_reserved_percent
        else:
            mount_size = get_filesystem_size(mp_path)[1]
            expected_reserved_percent = 98

        mp['expected_reserved_percent'] = expected_reserved_percent
        mp['mount_size'] = mount_size
        mp['real_mountpoint'] = mp_path

    if find_mount_point(vpool_json['dtl']['dtl_path']) == "/":
        root_mps = [mp['expected_reserved_percent'] for mp in mount_points if mp['real_mountpoint'] == "/"]
        if root_mps:
            reserved_on_root += min(root_mps)
    scale = None
    if 80 < reserved_on_root < 160:
        scale = 2.0
    elif 160 < reserved_on_root < 320:
        scale = 4.0
    elif reserved_on_root >= 320:
        scale = 8.0

    print "mount_points: {0}".format(mount_points)

    result = dict()
    for mp in mount_points:
        if mp['real_mountpoint'] == "/" and scale is not None:
            mp['expected_reserved_percent'] /= scale
        reserved_size = human2bytes(mp['size'])
        reserved_percent = int(round(reserved_size * 100 / float(mp['mount_size'])))

        expected_reserved_percent = int(mp['expected_reserved_percent'])
        result[mp['real_mountpoint']] = {'expected': expected_reserved_percent,
                                         'actual': reserved_percent,
                                         'path': mp['path']}
    print result
    return result


def get_file_perms(file_path):
    """
    Get permissions for file

    @param file_path:    File Path
    @type file_path:     String

    @return:             String of octal no. e.g.: '0644'
    """

    st = os.stat(file_path)
    perms = oct(st.st_mode & (stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO))
    return perms


def is_service_running(service_name, host_name=None):
    cmd = "initctl list | grep {0} && initctl status {0} || true".format(service_name)
    if host_name is None:
        out = execute_command(cmd)[0]
    else:
        out = execute_command_on_node(host_name, cmd)
    return "start/running" in out


def is_volume_present_in_model(volume_name):
    """
    Check if vdisk is present on all nodes
    """
    status = {}
    for vsa in StorageRouterList.get_storagerouters():
        cmd = """python -c 'from ovs.dal.lists.vdisklist import VDiskList
print bool([vd for vd in VDiskList.get_vdisks() if vd.name == "{0}"])'""".format(volume_name)
        out = execute_command_on_node(vsa.ip, cmd)
        status[vsa.ip] = eval(out)

    return status


def check_voldrv_services(vpool_name, storagedrivers, running=True):
    voldrv_services = (pr + vpool_name for pr in ("ovs-volumedriver_", "ovs-dtl_"))
    for sd in storagedrivers:
        node = sd.storagerouter.ip
        for voldrv_service in voldrv_services:
            retries = 15
            while retries:
                if is_service_running(voldrv_service, node) == running:
                    break
                time.sleep(1)
                retries -= 1
            assert is_service_running(voldrv_service, node) == running,\
                "Service {0} is not {1} on node {2}".format(voldrv_service,
                                                            {True: "running", False: "stopped"}[running],
                                                            node)


def check_mountpoints(storagedrivers, is_present=True):
    for sd in storagedrivers:
        mount_point = sd.mountpoint
        node = sd.storagerouter.ip
        mp = 'ignore-not-mounted'
        retries = 20

        out = ''
        while retries:
            out = execute_command_on_node(node, "df | grep {0} || true".format(mount_point))
            for mp in out.splitlines():
                mp = mp.split()
                if len(mp) == 6:
                    mp = mp[5]
                    if mount_point == mp:
                        break
            time.sleep(1)
            retries -= 1

        assert (mount_point == mp) == is_present,\
            "Vpool mountpoint {0} is {1} mounted on node {2}\n{3}".format(mount_point,
                                                                          {True: "not", False: "still"}[is_present],
                                                                          node, out)


def validate_logstash_open_files_amount():
    # OVS-2638 - obsolete as logstash is no longer installed by default
    ls_proc_pid = None
    file_counters = {'libs': {'description': 'Lib Components', 'amount': 0, 'regex': '^.+\.jar$'},
                     'devs': {'description': 'Device Handles', 'amount': 0, 'regex': '^/dev/.+$'},
                     'sockets': {'description': 'Socket Handlers', 'amount': 0, 'regex': '^socket:.+$'},
                     'patterns': {'description': 'Logstash Patterns', 'amount': 0, 'regex': '^.+logstash/patterns.+$'},
                     'logs': {'description': 'Logging Files', 'amount': 0, 'regex': '^/var/log/.+$'},
                     'others': {'description': 'Other Files', 'amount': 0}}
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    for pid in pids:
        try:
            with open(os.path.join('/proc', pid, 'cmdline'), 'rb') as proc_cmdline_handler:
                proc_cmdline = proc_cmdline_handler.read()
                if re.match('^.+bin/java.+logstash/runner.rb.*$', proc_cmdline):
                    ls_proc_pid = pid
                    break
        except IOError:
            # proc already terminated
            continue

    assert ls_proc_pid is not None, "Logstash process not running. PID not found"

    of_path = os.path.join('/proc', ls_proc_pid, 'fd')
    open_files = os.listdir(of_path)
    for of in open_files:
        of_link = os.readlink(os.path.join(of_path, of))
        match_found = False
        for info in file_counters.values():
            if info.get('regex') and re.match(info['regex'], of_link):
                info['amount'] += 1
                match_found = True
                break
        if not match_found:
            file_counters['others']['amount'] += 1

    # Print info
    print '\nLogstash Process ID : {0}\n'.format(ls_proc_pid)
    of_total = 0
    for counter_info in file_counters.values():
        of_total += counter_info['amount']
        print 'Amount of {0} : {1} (files)'.format(counter_info['description'],
                                                   counter_info['amount'])
    print '\nTotal amount of open files : {0}'.format(of_total)

    # Get maximum allowed open files
    max_allowed_of = None
    try:
        with open(os.path.join('/proc', ls_proc_pid, 'limits'), 'rb') as limits_file:
            for line in limits_file.readlines():
                if line.startswith('Max open files'):
                    line_parts = line.split()
                    max_allowed_of = int(line_parts[4])
                    break
        print 'Maximum allowed open files : {0}'.format(max_allowed_of)
    except:
        print 'Cannot retrieve the Maximum allowed open files'
    if max_allowed_of:
        assert of_total < 90 * max_allowed_of / 100,\
            'Reached more than 90% of Logstash maximum allowed open files : {0}'.format(max_allowed_of)


def setup_vpool(vpool_name, vpool_config='vpool'):
    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        api_add_vpool(vpool_name=vpool_name, vpool_config=vpool_config, config_cinder=True)
        vpool = VPoolList.get_vpool_by_name(vpool_name)

    return vpool


def get_vpool(vpool_name):
    vpool = VPoolList.get_vpool_by_name(vpool_name)
    return vpool


def validate_vpool_cleanup(vpool_name):
    pms = PMachineList.get_pmachines()
    detected_issues = ""
    vpool_path = '/mnt/' + vpool_name
    for pm in pms:
        logging.log(1, 'checking host: {0}'.format(pm.ip))

        # check if mountpoint is still present
        if os.path.isdir(vpool_path):
            detected_issues += '\n{0} - vpool_mountpoint {1} still present\n'.format(pm.ip, vpool_path)
            cmd = "ls -la {0}".format(vpool_path)
            out = execute_command_on_node(pm.ip, cmd)
            detected_issues += out

        # detected remaining storagedriver process
        cmd = "ps -ef | awk '/volumedriver_fs/ && /{0}/'".format(vpool_name)
        out = execute_command_on_node(pm.ip, cmd)
        output = ""
        for line in out.splitlines():
            if "awk" in line and "volumedriver_fs" in line:
                continue
            output += line
        if output:
            detected_issues += '\n\n{0} - volumedriver_fs process still running\n'.format(pm.ip)
            detected_issues += output

        # look for errors in storagedriver log file - only log these
        cmd = "cat -vet /var/log/ovs/volumedriver/{0}.log | tail -5000 | grep ' error '; echo true > /dev/null".format(vpool_name)
        out = execute_command_on_node(pm.ip, cmd)
        output = ""
        for line in out.splitlines():
            if "HierarchicalArakoon" in line:
                continue
            output += line
        if output:
            logging.log(1, '\n\n{0} - volumedriver log file contains errors\n'.format(pm.ip))
            logging.log(1, output)

        # look for fatal errors in storagedriver log file
        cmd = "cat -vet /var/log/ovs/volumedriver/{0}.log | tail -5000 | grep ' fatal '; echo true > /dev/null".format(vpool_name)
        out = execute_command_on_node(pm.ip, cmd)
        if out:
            detected_issues += '\n\n{0} - volumedriver log file contains fatal errors\n'.format(pm.ip)
            detected_issues += out

        assert len(detected_issues) == 0,\
            "Vpool cleanup for {0} was incomplete:\n{1}".format(vpool_name, detected_issues)


def create_testsuite_screenshot_dir(testsuite):
    dir_name = '/var/tmp/{0}_{1}'.format(testsuite, str(datetime.datetime.fromtimestamp(time.time())).replace(" ", "_").replace(":", "_").replace(".", "_"))
    execute_command(command='mkdir {0}'.format(dir_name))
    return dir_name


def get_physical_disks(ip):
    cmd = 'ls -la /dev/disk/by-id/'
    disk_by_id = dict()
    result = execute_command_on_node(ip, cmd)
    for entry in result.splitlines():
        if 'ata-' in entry:
            device = entry.split()
            disk_by_id[device[10][-3:]] = device[8]

    cmd = "lsblk -n -o name,type,size,rota"
    result = execute_command_on_node(ip, cmd)
    hdds = dict()
    ssds = dict()
    for entry in result.splitlines():
        disk = entry.split()
        disk_id = disk[0]
        if len(disk_id) > 2 and disk_id[0:2] in ['fd', 'sr', 'lo']:
            continue
        if disk[1] in 'disk':
            if disk[3] == '0':
                ssds[disk[0]] = {'size': disk[2], 'is_ssd': True, 'name': disk_by_id[disk[0]]}
            else:
                hdds[disk[0]] = {'size': disk[2], 'is_ssd': False, 'name': disk_by_id[disk[0]]}
    return hdds, ssds


def get_loops(ip):
    cmd = 'lsblk'
    loop_devices = []
    result = execute_command_on_node(ip, cmd)
    for entry in result.splitlines():
        if 'loop' in entry:
            device = entry.split()
            loop_devices.append(device[0])
    return loop_devices
