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

from ci.helpers.vdisk import VDiskHelper
from ovs.log.log_handler import LogHandler
from ci.helpers.backend import BackendHelper
from ci.validate.roles import RoleValidation
from ci.validate.vpool import VPoolValidation
from ci.validate.backend import BackendValidation
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.configuration import Configuration
from ci.helpers.exceptions import DirectoryNotFoundError, ArakoonClusterNotFoundError

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

        return func(*args, **kwargs)
    return validate


def required_cluster_basedir(func):
    """
    Validate if a directory exists for a new cluster

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # check if alba backend exists or not
        if kwargs['cluster_basedir'] and kwargs['storagerouter_ip']:
            client = SSHClient(kwargs['storagerouter_ip'], username='root')
            if client.dir_exists(kwargs['cluster_basedir']):
                return func(*args, **kwargs)
            else:
                raise DirectoryNotFoundError("Required base_dir `{0}` not found on storagerouter `{1}`"
                                             .format(kwargs['cluster_basedir'], kwargs['storagerouter_ip']))
        else:
            raise AttributeError("Missing parameter(s): cluster_basedir or storagerouter_ip")

    return validate


def required_arakoon_cluster(func):
    """
    Validate if a directory exists for a new cluster

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # check if arakoon cluster exists or not
        if kwargs['cluster_name']:
            if kwargs['cluster_name'] in list(Configuration.list('ovs/arakoon')):
                return func(*args, **kwargs)
            else:
                raise ArakoonClusterNotFoundError("Arakoon cluster does not exists: {0}".format(kwargs['cluster_name']))
        else:
            raise AttributeError("Missing parameter: cluster_name")

    return validate


def required_preset(func):
    """
    Validate preset exists on existing alba backend

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # check if preset exists or not on existing alba backend
        if kwargs['albabackend_name'] and kwargs['preset_name']:
            BackendHelper.get_preset_by_albabackend(kwargs['preset_name'], kwargs['albabackend_name'])
        else:
            raise AttributeError("Missing parameter: albabackend_name or preset_name")

        return func(*args, **kwargs)
    return validate


def required_vdisk(func):
    """
    Validate if vdisk exists on a vpool

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # check if preset exists or not on existing alba backend
        if "vpool_name" in kwargs and "vdisk_name" in kwargs:
            VDiskHelper.get_vdisk_by_name(vdisk_name=kwargs['vdisk_name'], vpool_name=kwargs['vpool_name'])
        elif "vdisk_guid" in kwargs:
            VDiskHelper.get_vdisk_by_guid(kwargs['vdisk_guid'])
        else:
            raise AttributeError("Missing parameter: vdisk_name or vpool_name")

        return func(*args, **kwargs)
    return validate


def required_vtemplate(func):
    """
    Validate if vdisk is a vTemplate

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # check if preset exists or not on existing alba backend
        if kwargs['vpool_name'] and kwargs['vdisk_name']:
            if not VDiskHelper.get_vdisk_by_name(vdisk_name=kwargs['vdisk_name'], vpool_name=kwargs['vpool_name'])\
                    .is_vtemplate:
                error_msg = "Given vDisk `{0}` on vPool `{1}` is not a vTemplate".format(kwargs['vdisk_name'],
                                                                                         kwargs['vpool_name'])
                LOGGER.error(error_msg)
                raise RuntimeError(error_msg)
        else:
            raise AttributeError("Missing parameter: vdisk_name or vpool_name")

        return func(*args, **kwargs)
    return validate


def required_snapshot(func):
    """
    Validate if snapshot exists for vdisk

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # check if snapshot_id is set, if so it has to be checked if the snapshot actually exists
        if 'snapshot_id' in kwargs:
            if kwargs['snapshot_id'] and kwargs['vpool_name'] and kwargs['vdisk_name']:
                VDiskHelper.get_snapshot_by_guid(snapshot_guid=kwargs['snapshot_id'], vdisk_name=kwargs['vdisk_name'],
                                                 vpool_name=kwargs['vpool_name'])
            else:
                raise AttributeError("Missing parameter: snapshot_id, vpool_name or vdisk_name")

        return func(*args, **kwargs)
    return validate


def check_vpool(func):
    """
    Validate if a vPool is already deployed on a certain storagerouter

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # if the vpool is not yet created, return the function
        if 'storagerouter_ip' in kwargs and 'vpool_name' in kwargs:
            if not VPoolValidation.check_vpool_on_storagerouter(storagerouter_ip=kwargs['storagerouter_ip'],
                                                                vpool_name=kwargs['vpool_name']):
                return func(*args, **kwargs)
            else:
                return
        else:
            raise AttributeError("Missing parameter: storagerouter_ip or vpool_name")
    return validate


def check_linked_backend(func):
    """
    Validate if a backend is already linked to a global backend

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # if the vpool is not yet created, return the function
        if 'albabackend_name' in kwargs and 'globalbackend_name' in kwargs:
            if not BackendValidation.check_linked_backend(albabackend_name=kwargs['albabackend_name'],
                                                          globalbackend_name=kwargs['globalbackend_name']):
                return func(*args, **kwargs)
            else:
                return
        else:
            raise AttributeError("Missing parameter: albabackend_name or globalbackend_name")
    return validate


def filter_osds(func):
    """
    Validate if osds / disks are available for alba usage

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        # if the vpool is not yet created, return the function
        if 'target' in kwargs and 'disks' in kwargs:
            LOGGER.info("Starting to filtering the following disks: {0}".format(kwargs['disks']))
            disks = BackendValidation.check_available_osds_on_asdmanager(ip=kwargs['target'], disks=kwargs['disks'])
            # if no disks are available anymore skip the wrapped func
            if len(disks.keys()) != 0:
                LOGGER.info("Filtered the osds from {0} to {1}".format(kwargs['disks'], disks))
                kwargs['disks'] = disks
                return func(*args, **kwargs)
            else:
                LOGGER.error("Skipped wrapped function after filtering osds list, because its empty: {0}".format(disks))
                return
        else:
            raise AttributeError("Missing parameter: target or disks")
    return validate


def check_role_on_disk(func):
    """
    Validate role(s) on disk

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        if kwargs['storagerouter_ip'] and kwargs['roles'] and kwargs['diskname']:
            if not RoleValidation.check_role_on_disk(kwargs['roles'], kwargs['storagerouter_ip'], kwargs['diskname']):
                # if the disk is not yet initialized with the required role execute the method
                return func(*args, **kwargs)
            else:
                return
        else:
            raise AttributeError("Missing parameter: storagerouter_ip, roles or diskname")
    return validate


def check_backend(func):
    """
    Check if a backend is already present

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        if kwargs['backend_name']:
            if not BackendValidation.check_backend(kwargs['backend_name']):
                # if the backend is not yet created, create it
                return func(*args, **kwargs)
            else:
                return
        else:
            raise AttributeError("Missing parameter: backend_name")
    return validate


def check_preset(func):
    """
    Check if a preset is already present on a backend

    :param func: function
    :type func: Function
    """

    def validate(*args, **kwargs):
        if kwargs['albabackend_name'] and kwargs['preset_details']:
            if not BackendValidation.check_preset_on_backend(preset_name=kwargs['preset_details']['name'],
                                                             albabackend_name=kwargs['albabackend_name']):
                # if the preset is not yet created, create it
                return func(*args, **kwargs)
            else:
                return
        else:
            raise AttributeError("Missing parameter: backend_name")
    return validate
