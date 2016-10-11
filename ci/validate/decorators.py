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

from functools import wraps
from ci.helpers.disk import DiskHelper
from ovs.log.log_handler import LogHandler
from ci.helpers.backend import BackendHelper
from ci.validate.roles import RoleValidation

LOGGER = LogHandler.get(source='decorators', name="ci_decorator")
LOCATION_OPTIONS = ['GLOBAL', 'LOCAL']


def required_roles(roles, location="GLOBAL"):
    """
    Decorator that checks if the required roles are available on the cluster or on a local storagerouter

    :param roles: the required roles
    :type roles: list
    :param location:
        * GLOBAL: checks the whole cluster if certain roles are available
        * LOCAL: checks the local storagerouter if certain roles are available
    :type location: str
    :return:
    """
    def validate_required_roles(func):
        def validate(*args, **kwargs):
            if location in LOCATION_OPTIONS:
                if location == "GLOBAL":
                    # check on cluster if roles are available
                    RoleValidation.check_required_roles(roles)
                else:
                    # check on certain node if roles are available
                    RoleValidation.check_required_roles(roles, kwargs['storagerouter_ip'], "LOCAL")
            else:
                error_msg = "Chosen location `{0}` does not exists! It should be one of these options `{1}`"\
                    .format(location, LOCATION_OPTIONS)
                LOGGER.error(error_msg)
                raise RuntimeError(error_msg)
            return func(*args, **kwargs)
        return validate
    return validate_required_roles


def required_backend(func):
    """
    Validate if alba backend exists

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # check if alba backend exists or not
        if type(kwargs['albabackend_name']) == list:
            for albabackend in kwargs['albabackend_name']:
                BackendHelper.get_albabackend_by_name(albabackend)
        elif type(kwargs['albabackend_name']) == str or type(kwargs['albabackend_name']) == unicode:
            BackendHelper.get_albabackend_by_name(kwargs['albabackend_name'])
        else:
            error_msg = "Type `{0}` is not supported to check the required backend(s)"\
                .format(type(kwargs['albabackend_name']))
            LOGGER.error(error_msg)
            raise TypeError(error_msg)

        func(*args, **kwargs)
    return validate
