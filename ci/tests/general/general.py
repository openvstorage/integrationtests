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
import paramiko
import ConfigParser
from ci.scripts import debug
from nose.plugins.skip import SkipTest
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.dal.lists.vdisklist import VDiskList
from ovs.dal.lists.vmachinelist import VMachineList
from ovs.extensions.generic.sshclient import SSHClient
from ovs.lib.setup import SetupController

if not hasattr(sys, "debugEnabled"):
    sys.debugEnabled = True
    debug.listen()

logging.getLogger("paramiko").setLevel(logging.WARNING)

current_test = None    # Used by each individual test to indicate which test is running and is used by 'take_screenshot'
screenshot_dir = None  # Used by each testsuite to indicate which testsuite is running and is used by 'take_screenshot'

AUTOTEST_DIR = os.path.join(os.sep, "opt", "OpenvStorage", "ci")
CONFIG_DIR = os.path.join(AUTOTEST_DIR, "config")
SCRIPTS_DIR = os.path.join(AUTOTEST_DIR, "scripts")
TESTS_DIR = os.path.join(AUTOTEST_DIR, "tests")

AUTOTEST_CFG_FILE = os.path.join(CONFIG_DIR, "autotest.cfg")
OS_MAPPING_CFG_FILE = os.path.join(CONFIG_DIR, "os_mapping.cfg")


def get_config():
    """
    Get autotest config
    """
    # @TODO: Replace by ETCD
    autotest_config = ConfigParser.ConfigParser()
    autotest_config.read(AUTOTEST_CFG_FILE)
    return autotest_config


def save_config(config):
    """
    Save autotest config file
    :param config: Configuration to save
    """
    # @TODO: Replace by ETCD
    with open(AUTOTEST_CFG_FILE, "wb") as autotest_config:
        config.write(autotest_config)


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


def get_ips():
    """
    Get node ips based on model information
    """
    ips = []
    from ovs.dal.lists.pmachinelist import PMachineList
    pms = PMachineList.get_pmachines()
    for machine in pms:
        ips.append(str(machine.ip))
    return ips


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

    from ci.tests.general import general_hypervisor
    from ci.tests.vpool.general_vpool import GeneralVPool
    for vpool in GeneralVPool.get_vpools():
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


            vpool.remove_vpool()

            if general_hypervisor.get_hypervisor_type() == "VMWARE":
                hypervisor_info = general_hypervisor.get_hypervisor_info()
                ssh_con = get_remote_ssh_connection(*hypervisor_info)[0]
                cmd = "esxcli storage nfs remove -v {0}".format(vpool.name)
                ssh_con.exec_command(cmd)

            vmachines = VMachineList.get_vmachines()
            for vmachine in vmachines:
                logging.log(1, 'WARNING: Removing leftover vmachine: {0}'.format(vmachine.name))
                vmachine.delete()
    # remove_alba_namespaces()


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


def apply_disk_layout(disk_layout):
    # @TODO: remove this when http://jira.cloudfounders.com/browse/OVS-1336 is fixed
    ovs_fstab_start = "BEGIN Open vStorage"
    execute_command("sed -i '/{0}/d' /etc/fstab".format(ovs_fstab_start))

    print "Disk layout to apply: {0}".format(disk_layout)

    grid_ip = get_config().get("main", "grid_ip")
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
    if get_config().getboolean("main", "cleanup") is not True:
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


def get_test_level():
    """
    Read test level from config file
    """
    config = get_config()
    return config.get(section="main", option="testlevel")


def set_test_level(test_level):
    """
    Set test level : 1,2,3,8-12,15
    :param test_level: Tests to execute
    """
    testlevel_regex = "^([0-9]|[1-9][0-9])([,-]([1-9]|[1-9][0-9])){0,}$"
    if not re.match(testlevel_regex, test_level):
        print('Wrong testlevel specified\neg: 1,2,3,8-12,15')
        return False

    config = get_config()
    config.set(section="main", option="testlevel", value=test_level)
    save_config(config)

    return True


def list_os():
    """
    List os' configured in os_mapping
    """

    os_mapping_config = ConfigParser.ConfigParser()
    os_mapping_config.read(OS_MAPPING_CFG_FILE)

    return os_mapping_config.sections()


def get_os_info(os_name):
    """
    Get info about an os configured in os_mapping
    :param os_name: Name of operating system to retrieve information for
    """
    os_mapping_config = ConfigParser.ConfigParser()
    os_mapping_config.read(OS_MAPPING_CFG_FILE)

    if not os_mapping_config.has_section(os_name):
        print("No configuration found for os {0} in config".format(os_name))
        return

    return dict(os_mapping_config.items(os_name))


def set_os(os_name):
    """
    Set current os to be used by tests
    :param os_name: Name of operating system to set
    """
    os_list = list_os()
    if os_name not in os_list:
        print("Invalid os specified, available options are {0}".format(str(os_list)))
        return False

    config = get_config()
    config.set(section="main", option="os", value=os_name)
    save_config(config)

    return True


def get_os():
    """
    Retrieve current configured os for autotests
    """
    return get_config().get(section="main", option="os")


def set_template_server(template_server):
    """
    Set current template server to be used by tests
    :param template_server: Template server to set
    """

    config = get_config()
    config.set(section="main", option="template_server", value=template_server)
    save_config(config)

    return True


def get_template_server():
    """
    Retrieve current configured template server for autotests
    """
    return get_config().get(section="main", option="template_server")


def get_username():
    """
    Get username to use in tests
    """
    return get_config().get(section="main", option="username")


def set_username(username):
    """
    Set username to use in tests
    :param username: Username to set
    """
    config = get_config()
    config.set(section="main", option="username", value=username)
    save_config(config)

    return True


def get_password():
    """
    Get password to use in tests
    """
    return get_config().get(section="main", option="username")


def set_password(password):
    """
    Set password to use in tests
    :param password: Password to set
    """
    config = get_config()
    config.set(section="main", option="password", value=password)
    save_config(config)

    return True
