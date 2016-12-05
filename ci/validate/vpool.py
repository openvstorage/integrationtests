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

from ci.helpers.storagerouter import StoragerouterHelper
from ci.helpers.storagedriver import StoragedriverHelper
from ovs.log.log_handler import LogHandler


class VPoolValidation(object):

    LOGGER = LogHandler.get(source="validate", name="ci_role_validate")

    def __init__(self):
        pass

    @staticmethod
    def check_vpool_on_storagerouter(storagerouter_ip, vpool_name):
        """
        Check if the required roles are satisfied

        :param storagerouter_ip: ip address of a storagerouter
        :type storagerouter_ip: str
        :param vpool_name: name of a vpool
        :type vpool_name: str
        :return: is vpool available? True = YES, False = NO
        :rtype: bool
        """

        storagerouter = StoragerouterHelper.get_storagerouter_by_ip(storagerouter_ip)
        try:
            return next(True for storagedriver in
                        StoragedriverHelper.get_storagedrivers_by_storagerouterguid(storagerouter.guid)
                        if vpool_name in storagedriver.name)
        except StopIteration:
            return False
