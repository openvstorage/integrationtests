import os
import sys
import paramiko
import random
import urllib
import shutil
import inspect
import subprocess
from nose.plugins.skip import SkipTest

from ovs.dal.lists          import vmachinelist, storagerouterlist, vpoollist
import general_hypervisor
from ci                     import autotests
from ovs.extensions.grid    import manager

ScriptsDir = os.path.join(os.sep, "opt", "OpenvStorage", "ci", "scripts")
sys.path.append(ScriptsDir)
import debug

if not hasattr(sys, "debugEnabled"):
    sys.debugEnabled = True
    debug.listen()


def execute_command(command):
    childProc = subprocess.Popen(command,
                                 shell=True,
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

    (out, error) = childProc.communicate()
    return out, error


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
    ip = execute_command("""ip a | grep "virbr.*:" -A 2 | awk '/inet/ {print $2;}'""")[0].strip()
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
    vpool_name  = autotests._getConfigIni().get("vpool", "vpool_name")

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
            for d in os.listdir(mountpoint):
                if d.startswith(machinename):
                    shutil.rmtree(os.path.join(mountpoint, d))
            for mac in env_macs:
                mac_path = os.path.join(mountpoint, mac)
                if os.path.exists(mac_path):
                    for f in os.listdir(mac_path):
                        os.remove(os.path.join(mac_path, f))

        for sdg in vpool.storagedrivers_guids:
            manager.Manager.remove_vpool(sdg)

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

