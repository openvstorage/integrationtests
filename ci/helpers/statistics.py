# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

from ovs.log.log_handler import LogHandler
from ovs.extensions.generic.sshclient import SSHClient


class StatisticsHelper(object):
    """
    Statistics Helper class
    """
    LOGGER = LogHandler.get(source='helpers', name="ci_statistics")

    def __init__(self):
        pass

    @staticmethod
    def get_current_memory_usage(storagerouter_ip):
        """
        get residential memory usage of a certain storagerouter (through free -m)

        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :return: (current usage, max. total usage)
        :rtype: tuple
        """
        client = SSHClient(storagerouter_ip, username='root')
        result = client.run("MEM=$(free -m | tr -s ' ' | grep Mem); "
                            "echo $MEM | cut -d ' ' -f 3; echo $MEM | cut -d ' ' -f 2", allow_insecure=True).split()
        return int(result[0]), int(result[1])

    @staticmethod
    def get_current_memory_usage_of_process(storagerouter_ip, pid):
        """
        get residential memory usage of a certain storagerouter (through /proc/<PID>/status)

        VmPeak:   8110620 kB
        VmSize:  3252752 kB
        VmLck:   0 kB
        VmPin:   0 kB
        VmHWM:   4959820 kB
        VmRSS:   570764 kB
        VmData:  3019468 kB
        VmStk:   136 kB
        VmExe:   12464 kB
        VmLib:   58852 kB
        VmPTE:   2644 kB
        VmPMD:   24 kB
        VmSwap:  394224 kB

        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :param pid: process ID of the process you want to monitor
        :type pid: int
        :return: current usage
        :rtype: str
        """
        client = SSHClient(storagerouter_ip, username='root')
        return client.run("grep Vm /proc/{0}/status | tr -s ' '".format(pid), allow_insecure=True)
