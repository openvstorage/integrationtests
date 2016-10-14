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
from ci.helpers.backend import BackendHelper
from ci.helpers.exceptions import AlbaBackendNotFoundError, PresetNotFoundError


class BackendValidation(object):

    LOGGER = LogHandler.get(source="validate", name="ci_backend_validate")

    def __init__(self):
        pass

    @staticmethod
    def check_preset_on_backend(preset_name, albabackend_name):
        """
        Check if a preset is available on a backend

        :param preset_name: name of a preset
        :type preset_name: str
        :param albabackend_name: name of a backend
        :type albabackend_name: str
        :return: is vpool available? True = YES, False = NO
        :rtype: bool
        """

        try:
            BackendHelper.get_preset_by_albabackend(preset_name, albabackend_name)
            return True
        except PresetNotFoundError:
            return False
        except AlbaBackendNotFoundError:
            return False
