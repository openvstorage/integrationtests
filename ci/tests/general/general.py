import os
import sys
import json
import time
import random
import urllib
import shutil
import inspect
import pexpect
import paramiko
import subprocess
from nose.plugins.skip import SkipTest

from ovs.dal.lists                      import vmachinelist, storagerouterlist, vpoollist
import general_hypervisor
from ci                                 import autotests
from ovs.lib.storagerouter              import StorageRouterController
from ovs.lib.setup                      import SetupController
from ovs.extensions.generic.sshclient   import SSHClient

ScriptsDir = os.path.join(os.sep, "opt", "OpenvStorage", "ci", "scripts")
sys.path.append(ScriptsDir)
import debug

if not hasattr(sys, "debugEnabled"):
    sys.debugEnabled = True
    debug.listen()


def execute_command(command, wait = True, shell = True):
    childProc = subprocess.Popen(command,
                                 shell  = shell,
                                 stdin  = subprocess.PIPE,
                                 stdout = subprocess.PIPE,
                                 stderr = subprocess.PIPE)

    if not wait:
        return childProc.pid
    (out, error) = childProc.communicate()
    return out, error


def execute_command_on_node(host, command, password = None):
    cl = SSHClient.load(host, password = password)
    return cl.run(command)


def get_elem_with_val(iterable, key, value):
    """
    iterable : Iterable of dict items
    """
    return [e for e in iterable if e.get(key, "iNvAlId_VaLuE") == value]


def getTestsToRun():
    """
    Retrieves the tests to be executed in the testsuite (from autotest config file)

    @return:     List of numbers of tests to be executed
    @returntype: List of integers
    """

    tests      = autotests.getTestLevel()
    testsToRun = []
    if tests:
        for number in tests.split(','):
            if not number.find('-') >= 0:
                testsToRun.append(int(number))
            else:
                numbers = number.split('-')
                if int(numbers[0]) > int(numbers[1]):
                    hulp       = numbers[0]
                    numbers[0] = numbers[1]
                    numbers[1] = hulp

                testsToRun.append(int(numbers[0]))
                for k in range(int(numbers[0]) + 1, int(numbers[1]) + 1):
                    testsToRun.append(k)

    return sorted(list(set(testsToRun)))

def lineno():
    """Returns the current line number in our program."""
    return inspect.currentframe().f_back.f_lineno


def checkPrereqs(testCaseNumber, testsToRun):
    """
    Check whetever test needs to run or not
    @param testCaseNumber:    Number of testcase --> Used to determine if test needs to be executed
    @type testCaseNumber:     Integer

    @param testsToRun:        Number(s) of tests of a testsuite to execute
    @type testsToRun:         List of Integers

    @return:                  None
    """
    if 0 not in testsToRun and testCaseNumber not in testsToRun:
        raise SkipTest

def getTestsToRun(test_level):
    """
    Retrieves the tests to be executed in the testsuite (from autotest config file)

    @return:     List of numbers of tests to be executed
    @returntype: List of integers
    """
    tests      = test_level
    testsToRun = []
    if tests:
        for number in tests.split(','):
            if not number.find('-') >= 0:
                testsToRun.append(int(number))
            else:
                numbers = number.split('-')
                if int(numbers[0]) > int(numbers[1]):
                    hulp       = numbers[0]
                    numbers[0] = numbers[1]
                    numbers[1] = hulp

                testsToRun.append(int(numbers[0]))
                for k in range(int(numbers[0])+1,int(numbers[1])+1):
                    testsToRun.append(k)

    return sorted(list(set(testsToRun)))

def getRemoteSshCon(ipAddress, username, password):
    """
    """
    sshCon = paramiko.SSHClient()
    sshCon.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sshCon.connect(ipAddress, username = username, password = password, timeout  = 2)
    sftp = sshCon.open_sftp()
    return sshCon, sftp


def get_virbr_ip():
    ip = execute_command("ip a | awk '/inet/ && /virbr0/ {print $2}'")[0].strip()
    return ip


def get_local_vsa():
    local_ip_info =  execute_command("ip a")[0]
    for vsa in storagerouterlist.StorageRouterList.get_storagerouters():
        if vsa.ip in local_ip_info:
             return vsa

def getFunctionName(level = 0):
    """
    Returns the functionName of the test being executed currently

    @param level: Depth of path returned
    @type level:  Integer

    @return:      Name of the test
    @returntype:  String
    """
    return sys._getframe( level + 1 ).f_code.co_name


def cleanup():
    machinename = "AT_"
    vpool_name  = autotests.getConfigIni().get("vpool", "vpool_name")

    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    if vpool:
        hpv = general_hypervisor.Hypervisor.get(vpool.name)
        vm_names = [vm.name for vm in vmachinelist.VMachineList.get_vmachines()]
        for name in vm_names:
            vm = vmachinelist.VMachineList.get_vmachine_by_name(name)
            if not vm:
                continue
            vm = vm[0]
            if not vm.name.startswith(machinename):
                continue
            if vm.is_vtemplate:
                hpv.delete_clones(vm.name)
            hpv.delete(vm.name)

        env_macs = execute_command("""ip a | awk '/link\/ether/ {gsub(":","",$2);print $2;}'""")[0].splitlines()
        if vpool.storagedrivers:
            mountpoint = vpool.storagedrivers[0].mountpoint
            if os.path.exists(mountpoint):
                for d in os.listdir(mountpoint):
                    if d.startswith(machinename):
                        shutil.rmtree(os.path.join(mountpoint, d))
                for mac in env_macs:
                    mac_path = os.path.join(mountpoint, mac)
                    if os.path.exists(mac_path):
                        for f in os.listdir(mac_path):
                            os.remove(os.path.join(mac_path, f))

        for sdg in vpool.storagedrivers_guids:
            StorageRouterController.remove_storagedriver(sdg)

        if general_hypervisor.get_hypervisor_type() == "VMWARE":
            hypervisorInfo = autotests.getHypervisorInfo()
            ssh_con = getRemoteSshCon(*hypervisorInfo)[0]
            cmd = "esxcli storage nfs remove -v {0}".format(vpool.name)
            ssh_con.exec_command(cmd)


def add_vpool(browser):
    browser.add_vpool()

    if general_hypervisor.get_hypervisor_type() == "VMWARE":
        hypervisorInfo = autotests.getHypervisorInfo()
        ssh_con = getRemoteSshCon(*hypervisorInfo)[0]

        vpool_name  = browser.vpool_name
        vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
        storage_ip = vpool.storagedrivers[0].storage_ip

        cmd = "esxcli storage nfs add -H {0} -s /mnt/{1} -v {1}".format(storage_ip, vpool_name)
        os.write(1, cmd + "\n")
        _stdin, stdout, stderr = ssh_con.exec_command(cmd)
        os.write(1, str(stdout.readlines()))
        os.write(1, str(stderr.readlines()))


def remove_vpool(browser):
    vpool_name  = browser.vpool_name
    browser.remove_vpool(vpool_name)

    if general_hypervisor.get_hypervisor_type() == "VMWARE":
        hypervisorInfo = autotests.getHypervisorInfo()
        ssh_con = getRemoteSshCon(*hypervisorInfo)[0]

        _stdin, stdout, _stderr = ssh_con.exec_command("esxcli storage nfs list")
        out = "\n".join(stdout.readlines())
        if vpool_name in out:

            cmd = "esxcli storage nfs remove -v {0}".format(vpool_name)
            stdin, stdout, stderr = ssh_con.exec_command(cmd)
            print stdout.readlines()
            print stderr.readlines()


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


def get_filesystem_size(mountpoint):
    statvfs = os.statvfs(mountpoint)
    full_size = statvfs.f_frsize * statvfs.f_blocks
    available_size = statvfs.f_bavail * statvfs.f_frsize
    used_size = (statvfs.f_blocks - statvfs.f_bfree) * statvfs.f_frsize
    nonroot_total  = available_size + used_size

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
    SYMBOLS = {
                'customary'     : ('B', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y'),
                'customary_ext' : ('byte', 'kilo', 'mega', 'giga', 'tera', 'peta', 'exa',
                                   'zetta', 'iotta'),
                'iec'           : ('Bi', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB'),
                'iec_ext'       : ('byte', 'kibi', 'mebi', 'gibi', 'tebi', 'pebi', 'exbi',
                                   'zebi', 'yobi'),
               }

    init = s
    num = ""
    while s and s[0:1].isdigit() or s[0:1] == '.':
        num += s[0]
        s = s[1:]
    num = float(num)
    letter = s.strip()
    for name, sset in SYMBOLS.items():
        if letter in sset:
            break
    else:
        if letter == 'k':
            # treat 'k' as an alias for 'K' as per: http://goo.gl/kTQMs
            sset = SYMBOLS['customary']
            letter = letter.upper()
        else:
            raise ValueError("can't interpret %r" % init)
    prefix = {sset[0]:1}
    for i, s in enumerate(sset[1:]):
        prefix[s] = 1 << (i+1)*10
    return int(num * prefix[letter])


def api_add_vpool(vpool_name          = None,
                  vpool_type          = None,
                  vpool_host          = None,
                  vpool_port          = None,
                  vpool_access_key    = None,
                  vpool_secret_key    = None,
                  vpool_temp_mp       = None,
                  vpool_md_mp         = None,
                  vpool_readcache1_mp = None,
                  vpool_readcache2_mp = None,
                  vpool_writecache_mp = None,
                  vpool_foc_mp        = None,
                  vpool_bfs_mp        = None,
                  vpool_vrouter_port  = None,
                  vpool_storage_ip    = None,
                  apply_to_all_nodes  = False):

    cfg = autotests.getConfigIni()

    local_vsa_ip = get_local_vsa().ip

    parameters = {}
    parameters['storagerouter_ip']      = local_vsa_ip
    parameters['vpool_name']            = vpool_name          or cfg.get("vpool", "vpool_name")
    parameters['type']                  = vpool_type          or cfg.get("vpool", "vpool_type")
    parameters['connection_host']       = vpool_host          or cfg.get("vpool", "vpool_host")
    parameters['connection_timeout']    = 600
    parameters['connection_port']       = vpool_port          or cfg.get("vpool", "vpool_port")
    parameters['connection_username']   = vpool_access_key    or cfg.get("vpool", "vpool_access_key")
    parameters['connection_password']   = vpool_secret_key    or cfg.get("vpool", "vpool_secret_key")
    parameters['mountpoint_temp']       = vpool_temp_mp       or cfg.get("vpool", "vpool_temp_mp")
    parameters['mountpoint_md']         = vpool_md_mp         or cfg.get("vpool", "vpool_md_mp")
    parameters['mountpoint_readcache1'] = vpool_readcache1_mp or cfg.get("vpool", "vpool_readcache1_mp")
    parameters['mountpoint_readcache2'] = vpool_readcache2_mp or cfg.get("vpool", "vpool_readcache2_mp")
    parameters['mountpoint_writecache'] = vpool_writecache_mp or cfg.get("vpool", "vpool_writecache_mp")
    parameters['mountpoint_foc']        = vpool_foc_mp        or cfg.get("vpool", "vpool_foc_mp")
    parameters['mountpoint_bfs']        = vpool_bfs_mp        or cfg.get("vpool", "vpool_bfs_mp")
    parameters['vrouter_port']          = vpool_vrouter_port  or cfg.get("vpool", "vpool_vrouter_port")
    parameters['storage_ip']            = vpool_storage_ip    or cfg.get("vpool", "vpool_storage_ip")

    print "Adding Vpool: "
    print parameters

    if apply_to_all_nodes:
        storagerouters = [(sr.ip, sr.machine_id) for sr in storagerouterlist.StorageRouterList.get_storagerouters()]
        StorageRouterController.update_storagedrivers([], storagerouters, parameters)
    else:
        StorageRouterController.add_vpool(parameters)

    return parameters


def api_remove_vpool(vpool_name):
    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    if not vpool:
        return

    local_vsa = get_local_vsa()

    for sd in vpool.storagedrivers:
        mountpoint = ""
        if sd.cluster_ip == local_vsa.ip:
            mountpoint = sd.mountpoint
        StorageRouterController.remove_storagedriver(sd.guid)
        if mountpoint:
            assert not os.path.exists(mountpoint), "Mountpoint {0} of vpool still exists after removing storage driver".format(mountpoint)


def apply_disk_layout(disk_layout):

    #@TODO: remove this when http://jira.cloudfounders.com/browse/OVS-1336 is fixed
    ovs_fstab_start = "BEGIN Open vStorage"
    execute_command("sed -i '/{0}/d' /etc/fstab".format(ovs_fstab_start))

    client = SSHClient.load('127.0.0.1', 'rooter')
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
            assert mount, "{0}, device {1} was not mounted after issueing apply_flexible_disk_layout\nDisk Layout: {2}".format(mp, device, disk_layout)
        else:
            assert not mount, "DIR_ONLY {0} should not be mounted after isueing apply_flexible_disk_layout\nDisk Layout: {1}".format(mp, disk_layout)


def clean_disk_layout(disk_layout):
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


def validate_vpool_size_calculation(vpool_name, disk_layout, initial_part_used_space = {}):
    """

    @param vpool_name:                  Name of vpool
    @type vpool_name:                   String

    @param disk_layout:                 Disk layout dict
    @type disk_layout:                  Dict

    @param initial_part_used_space:     Dict with used space for each partition at the beggining of test
    @type initial_part_used_space:      Dict

    @return:             None
    """

    vpool = vpoollist.VPoolList.get_vpool_by_name(vpool_name)
    sd    = vpool.storagedrivers[0]

    with open("/opt/OpenvStorage/config/voldrv_vpools/{0}.json".format(vpool_name)) as vpool_json_file:
        vpool_json = json.load(vpool_json_file)

    mountpoints = vpool_json['content_addressed_cache']['clustercache_mount_points'] + vpool_json['scocache']['scocache_mount_points']
    real_mountpoints = [(mp['path'], find_mount_point(mp['path'])) for mp in mountpoints]

    all_on_root = [find_mount_point(d) == "/" for d in disk_layout]

    reserved_on_root = 0

    print "Mountpoints:"
    print mountpoints

    for mp in mountpoints:
        mp_path = os.path.dirname(mp['path'])
        dl = disk_layout[mp_path]
        dev_path = dl['device']
        real_mountpoint = None
        print "mp: " , str(mp)
        print "dl: ", str(dl)
        if dev_path == 'DIR_ONLY':
            real_mountpoint = find_mount_point(mp['path'])
            other_mountpoint = [rm for rm in real_mountpoints if rm[0] != mp['path'] and rm[1] == real_mountpoint]

            if other_mountpoint:
                if len(all_on_root) in [2, 3]:
                    if "sco" in mp['path']:
                        expected_reserved_percent = 20
                    else:
                        expected_reserved_percent = 49
                else:
                    expected_reserved_percent = 24
            else:
                expected_reserved_percent = 49

            mount_size = get_filesystem_size(real_mountpoint)[1] - initial_part_used_space[real_mountpoint]

            if real_mountpoint == "/":
                reserved_on_root += expected_reserved_percent

        else:
            mount_size = get_filesystem_size(mp_path)[1]

            expected_reserved_percent = 98

        mp['expected_reserved_percent'] = expected_reserved_percent
        mp['mount_size']                = mount_size
        mp['real_mountpoint']           = real_mountpoint

    if find_mount_point(vpool_json['failovercache']['failovercache_path']) == "/":
        root_mps = [mp['expected_reserved_percent'] for mp in mountpoints if mp['real_mountpoint'] == "/"]
        if root_mps:
            reserved_on_root += min(root_mps)
    scale = None
    if 80 < reserved_on_root < 160:
        scale = 2.0
    elif 160 < reserved_on_root < 320:
        scale = 4.0
    elif reserved_on_root >= 320:
        scale = 8.0


    for mp in mountpoints:
        if mp['real_mountpoint'] == "/" and scale is not None:
            mp['expected_reserved_percent'] /= scale
        reserved_size = human2bytes(mp['size'])
        reserved_percent = int(round(reserved_size * 100 / float(mp['mount_size'])))

        expected_reserved_percent = int(mp['expected_reserved_percent'])
        assert reserved_percent == expected_reserved_percent, "Expected {0} reserved percent but got {1}\nfor {2}".format(expected_reserved_percent, reserved_percent, str(mp))

