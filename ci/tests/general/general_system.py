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

"""
A general class dedicated to Service and ServiceType logic
"""

from ci.tests.general.general import General


class GeneralSystem(object):
    """
    A general class dedicated to system service logic
    Support for init(upstart) / systemd
    """

    INIT_SYSTEM = General.execute_command_on_node('127.0.0.1', 'cat /proc/1/comm')
    if INIT_SYSTEM not in ['init', 'systemd']:
        raise RuntimeError('Unsupported init system: {0}'.format(INIT_SYSTEM))

    @staticmethod
    def list_ovs_services(host='127.0.0.1'):
        if GeneralSystem.INIT_SYSTEM == 'init':
            return General.execute_command_on_node(host, "initctl list | grep ovs-*").splitlines()
        elif GeneralSystem.INIT_SYSTEM == 'systemd':
            return General.execute_command_on_node(host, "systemctl -l | grep ovs-").splitlines()

    @staticmethod
    def list_running_ovs_services(host='127.0.0.1'):
        if GeneralSystem.INIT_SYSTEM == 'init':
            return [s for s in GeneralSystem.list_ovs_services(host) if 'start/running' in s]
        elif GeneralSystem.INIT_SYSTEM == 'systemd':
            return [s for s in GeneralSystem.list_ovs_services(host) if 'loaded active' in s]

    @staticmethod
    def list_non_running_ovs_services(host='127.0.0.1'):
        if GeneralSystem.INIT_SYSTEM == 'init':
            return [s for s in GeneralSystem.list_ovs_services(host) if 'start/running' not in s]
        elif GeneralSystem.INIT_SYSTEM == 'systemd':
            return [s for s in GeneralSystem.list_ovs_services(host) if 'loaded active' not in s]
