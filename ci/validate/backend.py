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
from ci.helpers.asdmanager import ASDManagerClient
from ci.helpers.albanode import AlbaNodeHelper
from ci.helpers.exceptions import AlbaBackendNotFoundError, PresetNotFoundError, AlbaNodeNotFoundError


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

    @staticmethod
    def check_backend(backend_name):
        """
        Check if a backend is available on the cluster

        :param backend_name: name of a existing backend
        :type backend_name: str
        :return: if exists
        :rtype: bool
        """

        return BackendHelper.get_backend_by_name(backend_name) is not None

    @staticmethod
    def check_linked_backend(albabackend_name, globalbackend_name):
        """
        Check if a backend is already linked to a given global backend

        :param albabackend_name: name of a existing alba backend
        :type albabackend_name: str
        :param globalbackend_name: name of a existing global alba backend
        :type globalbackend_name: str
        :return: if link exists
        :rtype: bool
        """

        albabackend_guid = BackendHelper.get_alba_backend_guid_by_name(albabackend_name)
        globalbackend = BackendHelper.get_albabackend_by_name(globalbackend_name)

        return albabackend_guid in globalbackend.linked_backend_guids

    @staticmethod
    def check_available_osds_on_asdmanager(ip, disks):
        """
        Check if osds are available on asd_manager

        :param ip: ip pointing to a asd manager
        :type ip: str
        :param disks: dictionary of disks e.g. { "sdc": 2, "sdd": 2 }
        :type disks: dict
        :return: dict with available disks
        :rtype: dict
        """

        albanode = AlbaNodeHelper.get_albanode_by_ip(ip)

        if albanode is not None:
            # compare requested disks with available disks
            fetched_disks = ASDManagerClient(node=albanode).get_disks().values()
            available_disks = {}
            for disk, amount_asds in disks.iteritems():
                try:
                    # check if requested disk is present and available in fetched_disks
                    next(fetched_disk for fetched_disk in fetched_disks if
                         fetched_disk['device'].split('/')[2] == disk and fetched_disk['available'])

                    # add disk to available disks
                    available_disks[disk] = amount_asds
                    BackendValidation.LOGGER.info("Disk `{0}` is available on node `{1}`!".format(ip, disk))
                except StopIteration:
                    BackendValidation.LOGGER.error("Disk `{0}` is NOT available on node `{1}`!".format(ip, disk))

            BackendValidation.LOGGER.info("The following disks are available for use on `{0}`: {1}"
                                          .format(ip, available_disks))

            return available_disks
        else:
            error_msg = "Alba node with ip `{0}` was not found!".format(ip)
            BackendValidation.LOGGER.error(error_msg)
            raise AlbaNodeNotFoundError(error_msg)

