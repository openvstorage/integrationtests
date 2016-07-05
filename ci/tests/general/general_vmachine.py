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
A general class dedicated to vMachine logic
"""

from ci.tests.general.general_hypervisor import GeneralHypervisor
from ci.tests.general.logHandler import LogHandler

class GeneralVMachine(object):
    """
    A general class dedicated to vMachine logic
    """
    logger = LogHandler.get('vmachines', name='vmachine')

    template_image = 'debian.qcow2'
    template_target_folder = '/var/tmp/templates/'
