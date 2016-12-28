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

from ci.helpers.disk import DiskHelper
from ovs.log.log_handler import LogHandler


class RoleValidation(object):

    LOGGER = LogHandler.get(source="validate", name="ci_role_validate")

    def __init__(self):
        pass

    @staticmethod
    def check_required_roles(roles, storagerouter_ip=None, location="GLOBAL"):
        """
        Check if the required roles are satisfied

        :param roles: the required roles
        :type roles: list
        :param storagerouter_ip: ip address of a storagerouter
        :type storagerouter_ip: str
        :param location:
            * GLOBAL: checks the whole cluster if certain roles are available
            * LOCAL: checks the local storagerouter if certain roles are available
        :type location: str
        :return: None
        """

        # fetch availabe roles
        if location == "LOCAL":
            # LOCAL
            available_roles = DiskHelper.get_roles_from_disks(storagerouter_ip=storagerouter_ip)
        else:
            # GLOBAL
            available_roles = DiskHelper.get_roles_from_disks()

        # check if required roles are satisfied
        req_roles = list(roles)
        for disk_roles in available_roles:
            for role in roles:
                if role in disk_roles:
                    # delete role in required roles if still exists
                    if role in req_roles:  # never gonna give you up...
                        req_roles.remove(role)

        if len(req_roles) != 0:
            error_msg = "Some required roles are missing `{0}` with location option `{1}`".format(req_roles, location)

            # append storagerouter_ip if searching on a LOCAL node
            if location == "LOCAL":
                error_msg += " on storagerouter {0}".format(storagerouter_ip)

            RoleValidation.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            return

    @staticmethod
    def check_role_on_disk(roles, storagerouter_ip, disk_name):
        """
        Check if a certain role(s) is available on a certain disk

        :param roles: roles that should or should not be on a disk
        :type roles: list
        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :param disk_name: name of a certain disk on the given storagerouter
        :type disk_name: str
        :return: if available on disk
        :rtype: bool
        """

        return set(DiskHelper.get_roles_from_disk(storagerouter_ip, disk_name)) == set(roles)
