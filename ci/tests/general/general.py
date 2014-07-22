import os
import sys
import paramiko
import random
import urllib
import inspect
import subprocess
from nose.plugins.skip import SkipTest

from ovs.dal.lists import vmachinelist, storagerouterlist


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