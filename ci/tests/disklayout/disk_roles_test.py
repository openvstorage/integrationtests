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

import logging
import re
from subprocess import check_output
from ovs.dal.exceptions import ObjectNotFoundException
from ci.tests.general.general import General
from ovs.extensions.generic.system import System
from ci.tests.general.logHandler import LogHandler
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_fstab import FstabHelper
from ci.tests.general.general_network import GeneralNetwork
from ci.tests.general.general_storagerouter import GeneralStorageRouter

logger = LogHandler.get('disklayout', name='alba')


class TestDiskRoles(object):
    """
    Disk roles testsuite
    Testing situations covered by this class:
     - Adding a role to a disk
     - Removing all roles of a disk
     - Appending a role to existing role on a disk
     - Remove a number of roles and leave x roles behind
    These tests can run from a config file that has the following markup:
    {
        ip: {
            "disks": [{
                "disk_name": "sda",
                "roles": ["DB"]
            }]
            }
    }
    """

    logger = logging.getLogger('test_disk_roles')

    #########
    # HELPERS #
    #########

    @staticmethod
    def set_roles_from_config(config, operation_type='SET'):
        """
        :param config: Configuration file containing all of the required information
        :type config: dict

        :param operation_type: type of action that will be executed (Example: 'APPEND' or 'SET')
        :type operation_type: str

        :return: Returns a object with the partition guid and its roles
        :type: Object
        """
        # Validate input
        if not (operation_type == 'APPEND' or operation_type == 'SET'):
            raise ValueError('The specified type is not supported. Use "APPEND" or "SET"')
        # End validate input

        logger.info("Starting {0} of disk roles".format(operation_type))
        collection = {}

        for key, value in config.iteritems():
            # key = ip address
            # value = disks

            for disk_info in value['disks']:
                roles_list = disk_info['roles']
                disk_name = disk_info['disk_name']
                logger.info("Fetching disk with diskname '{0}' for ip '{1}'".format(disk_name, key))
                disk = GeneralStorageRouter().get_disk_by_ip(disk_name, key)
                logger.info("Fetching or creating new partitions for disk '{0}'".format(disk.guid))
                partition = GeneralDisk.partition_disk(disk)
                new_roles_list = None
                if len(partition.roles) > 0:
                    original_roles = partition.roles
                    logger.info("Found roles '{0}' on partition '{1}'".format(original_roles, partition.guid))
                    new_roles_list = list(roles_list)
                    for role in original_roles:
                        if role not in new_roles_list:
                            new_roles_list.append(role)
                logger.info("Adding roles '{0}' to partition '{1}'".format(roles_list, partition.guid))
                collection[partition.guid] = roles_list
                if operation_type == "APPEND":
                    GeneralDisk.adjust_disk_role(partition, roles_list, 'APPEND')
                    if new_roles_list:
                        collection[partition.guid] = new_roles_list
                elif operation_type == "SET":
                    GeneralDisk.adjust_disk_role(partition, roles_list, 'SET')
        return collection

    @staticmethod
    def _umount(mountpoint):
        """
        Unmount the given partition
        :param mountpoint: Location where the mountpoint is mounted
        :type mountpoint: str
        :return:
        """
        try:
            check_output('umount {0}'.format(mountpoint), shell=True)
        except Exception:
            logger.exception('Unable to umount mountpoint {0}'.format(mountpoint))
            raise RuntimeError('Could not unmount {0}'.format(mountpoint))

    @staticmethod
    def _remove_filesystem(device, alias_part_label):
        """
        :param alias_part_label: eg /dev/disk/by-partlabel/ata-QEMU_HARDDISK_QM00011
        :type alias_part_label: str
        :return:
        """
        try:
            partition_cmd = "udevadm info --name={0} | awk -F '=' '/ID_PART_ENTRY_NUMBER/{{print $NF}}'".format(
                alias_part_label)
            partition_number = check_output(partition_cmd, shell=True)
            format_cmd = 'parted {0} rm {1}'.format(device, partition_number)
            check_output(format_cmd, shell=True)
        except Exception:
            logger.exception('Unable to remove filesystem of {0}'.format(alias_part_label))
            raise RuntimeError('Could not remove filesystem of {0}'.format(alias_part_label))

    @staticmethod
    def remove_roles_from_config(config, number_of_roles_to_remain=0):
        """

        :param config: Configuration file containing all of the required information
        :type config: dict

        :param number_of_roles_to_remain: how roles may still be defined on the partition. The first 'number_of_roles_to
        _remain' will remain.
        :type number_of_roles_to_remain: int

        :return: Returns a object with the partition guid and its roles
        :type: Object
        """
        collection = {}
        # Remove disk roles
        logger.info("Starting removal of disk roles")
        for key, value in config.iteritems():
            for disk_info in value['disks']:
                disk_name = disk_info['disk_name']
                logger.info("Fetching disk with diskname '{0}' for ip '{1}'".format(disk_name, key))
                disk = GeneralStorageRouter().get_disk_by_ip(disk_name, key)
                logger.info("Fetching partition of disk '{0}'".format(disk.guid))
                partition = GeneralDisk.partition_disk(disk)
                if number_of_roles_to_remain == 0:
                    # When number_of_roles_to_remain ==0, everything should have been removed
                    remaining_roles = []
                    logger.info("Removing roles '{0}' from partition '{1}'".format(remaining_roles, partition.guid))
                    GeneralDisk.adjust_disk_role(partition, remaining_roles, 'SET')
                    # Set back to pristine condition:
                    # Unmount partition
                    logger.info("Umounting disk {2}".format(partition.roles, partition.guid, disk_name))
                    TestDiskRoles._umount(partition.mountpoint)
                    # Remove from fstab
                    logger.info(
                        "Removing {0} from fstab".format(partition.mountpoint, partition.guid, disk_name))
                    FstabHelper().remove_by_mountpoint(partition.mountpoint)
                    # Remove filesystem
                    logger.info(
                        "Removing filesystem on partition {0} on disk {1}".format(partition.guid, disk_name))
                    alias = partition.aliases[0]
                    device = '/dev/{0}'.format(disk_name)
                    TestDiskRoles._remove_filesystem(device, alias)
                    # Remove partition from model
                    logger.info("Removing partition {0} on disk {1} from model".format(partition.guid, disk_name))
                    partition.delete()
                else:
                    if len(partition.roles) < number_of_roles_to_remain:
                        logger.warning("Number of roles that should remain exceed the number of roles that are present!"
                                       " Keeping all roles instead!")
                        roles_list = partition.roles
                    else:
                        roles_list = partition.roles[number_of_roles_to_remain:]
                    remaining_roles = General.remove_list_from_list(partition.roles, roles_list)
                    logger.info("Removing roles '{0}' from partition '{1}'".format(remaining_roles, partition.guid))
                    GeneralDisk.adjust_disk_role(partition, remaining_roles, 'SET')
                # Will test if the role is an empty list
                collection[partition.guid] = remaining_roles
        return collection
        # End remove disk roles

    @staticmethod
    def validate_roles(collection):
        """

        :param collection: object containing the partition guid as key and the list of roles as value
        :type collection: Object

        :return: returns true or false based on the condition
        :type: boolean
        """
        # Start validation
        # Check if roles are the same as specified
        iterations = 0
        successful_iterations = 0
        logger.info("Starting validation of disk roles")
        for key, value in collection.iteritems():
            iterations += 1
            # Fetch partition matching key
            try:
                partition = GeneralDisk.get_disk_partition(key)
                # Check if roles are the same
                logger.info("Comparing roles on the partition '{0}'...".format(key))
                logger.info("Found '{0}' on partition and predefined roles: '{1}'".format(partition.roles, value))
                if sorted(partition.roles) == sorted(value):
                    successful_iterations += 1
                else:
                    logger.error("The role '{0}' for partition '{1}' was not set correctly!".format(value, key))
                    logger.error("Found '{0}' and expected '{1}'!".format(partition.roles, value))
            except ObjectNotFoundException:
                logger.info('Partition was removed meaning that all roles are deleted.')
                successful_iterations += 1
        return successful_iterations == iterations

    @staticmethod
    def extract_disk_name(pathstring):
        """
        :param pathstring: A string containing a path to a disk (Example: /dev/sda)
        :type pathstring

        :return: Returns the diskname without the path (Example: sda)
        :type: str
        """
        values = re.split(r'\/', pathstring)
        return values[len(values)-1]

    @staticmethod
    def get_first_unused_disk():
        disks = GeneralDisk.get_unused_disks()
        if disks[0]:
            return TestDiskRoles.extract_disk_name(disks[0])
        else:
            raise ValueError('No available disks, setup is invalid for testing!')

    #########
    # TESTS #
    #########

    @staticmethod
    def tdr_0001_add_append_remove_role_test(ip=None, configuration=None, number_of_roles_to_remain=0):
        """
        This test will add a DB role to the sda disk of the storage router with the given IP
        :param ip: IP address of a storage router. (Example:
        :type ip: str

        :param configuration: Dict that determines layout
        :type configuration: dict
        :return: None

        :param number_of_roles_to_remain: how roles may still be defined on the partition. The first
        'number_of_roles_to_remain' will remain.
        :type number_of_roles_to_remain: int
        """

        if not ip:
            ip = System.get_my_storagerouter().ip

        # Start input validation
        GeneralNetwork.validate_ip(ip)
        # End input validation

        # Start setup
        if configuration:
            config = configuration
        else:
            # Will use first unused disk
            config = {
                ip: {
                    "disks": [{
                        "disk_name": TestDiskRoles.get_first_unused_disk(),
                        "roles": ["WRITE", "SCRUB"]
                    }]
                }
            }
        collection = TestDiskRoles.set_roles_from_config(config, 'SET')
        # End setup

        # Start validation
        assert TestDiskRoles.validate_roles(collection), "Roles were not set according to the configuration!"
        # End validation

        collection = TestDiskRoles.set_roles_from_config(config, 'APPEND')
        # End setup
        # Start validation
        assert TestDiskRoles.validate_roles(collection), "Roles were not set according to the configuration!"
        # End validation
        # Remove disk roles
        collection = TestDiskRoles.remove_roles_from_config(config, number_of_roles_to_remain)
        # End remove disk roles

        # Start remove validation
        assert TestDiskRoles.validate_roles(collection), "Roles were not removed!"
        # End validation