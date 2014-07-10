import os
import sys
import paramiko
import random
import urllib
import subprocess
from nose.plugins.skip import SkipTest

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


def installOvftool():
    ovftoolUrl = "http://sso-qpackages-loch.cloudfounders.com/templates/openvstorage/VMware-ovftool-3.5.0-1274719-lin.x86_64.bundle"
    ovftoolLocalPath = os.path.join(os.sep, "tmp", os.path.basename(ovftoolUrl))
    execute_command("cd /tmp;wget {0}".format(ovftoolUrl))

    command = ["/bin/sh", ovftoolLocalPath]
    p = subprocess.Popen(command, stdout = subprocess.PIPE, stdin = subprocess.PIPE, stderr = subprocess.PIPE)
    p.communicate(input = '\nyes\n\n')

    execute_command("which ovftool")


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


def getRemoteSshCon(ipAddress, username, password):
    """
    """
    sshCon = paramiko.SSHClient()
    sshCon.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sshCon.connect(ipAddress, username = username, password = password, timeout  = 2)
    sftp = sshCon.open_sftp()
    return sshCon, sftp


def deployVmFromOva(name,
                    datastore,
                    ovaFile):
    """
    Deploy a vm from an ova template
    """

    command = "ovftool -ds={0} --noSSLVerify --acceptAllEulas --skipManifestCheck -n={1} --net:Public={2} {3} vi://{4}:{5}@{6}/"
    command = command.format(datastore,
                             name,
                             publicNetName,
                             ovaFile,
                             ESX_USERNAME,
                             ESX_PASSWORD,
                             ESX_IP)

