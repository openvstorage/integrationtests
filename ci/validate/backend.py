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

import ast
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
        :return: does preset exist on backend?
        :rtype: bool
        """

        try:
            BackendHelper.get_preset_by_albabackend(preset_name, albabackend_name)
            return True
        except PresetNotFoundError:
            return False
        except AlbaBackendNotFoundError:
            return False

    @staticmethod
    def check_policies_on_preset(preset_name, albabackend_name, policies):
        """
        Check if a preset is available on a backend

        :param preset_name: name of a preset
        :type preset_name: str
        :param policies: policies that should match with fetched preset
        :type policies: list
        :return: do given policies match with fetched preset
        :rtype: bool
        """

        preset_policies = BackendHelper.get_preset_by_albabackend(preset_name, albabackend_name)['policies']
        return [list(ast.literal_eval(policy)) for policy in preset_policies] == policies
