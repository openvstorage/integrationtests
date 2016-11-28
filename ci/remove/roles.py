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
from subprocess import check_output
from ovs.log.log_handler import LogHandler
from ci.helpers.fstab import FstabHelper
from ci.helpers.storagerouter import StoragerouterHelper
from ci.setup.roles import RoleSetup


class RoleRemover(object):

    LOGGER = LogHandler.get(source="remove", name="ci_role_remover")
    CONFIGURE_DISK_TIMEOUT = 300

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
            RoleRemover.LOGGER.exception('Unable to umount mountpoint {0}'.format(mountpoint))
            raise RuntimeError('Could not unmount {0}'.format(mountpoint))

    @staticmethod
    def _remove_filesystem(device, alias_part_label):
        """

        :param alias_part_label: eg /dev/disk/by-partlabel/ata-QEMU_HARDDISK_QM00011
        :type alias_part_label: str
        :return:
        """
        try:
            partition_cmd = "udevadm info --name={0} | awk -F '=' '/ID_PART_ENTRY_NUMBER/{{print $NF}}'".format(alias_part_label)
            partition_number = check_output(partition_cmd, shell=True)
            format_cmd = 'parted {0} rm {1}'.format(device, partition_number)
            check_output(format_cmd, shell=True)
        except Exception:
            RoleRemover.LOGGER.exception('Unable to remove filesystem of {0}'.format(alias_part_label))
            raise RuntimeError('Could not remove filesystem of {0}'.format(alias_part_label))

    @staticmethod
    def remove_role(ip, diskname, api):
        allowed_roles = ['WRITE', 'READ', 'SCRUB', 'DB']
        RoleRemover.LOGGER.info("Starting removal of disk roles.")

        # Fetch information
        storagerouter_guid = StoragerouterHelper.get_storagerouter_guid_by_ip(ip)
        disk = StoragerouterHelper.get_disk_by_ip(ip, diskname)
        # Check if there are any partitions on the disk, if so check if there is enough space
        if len(disk.partitions) > 0:
            for partition in disk.partitions:
                # Remove all partitions that have roles
                if set(partition.roles).issubset(allowed_roles) and len(partition.roles) > 0:
                    RoleRemover.LOGGER.info("Removing {0} from partition {1} on disk {2}".format(partition.roles, partition.guid, diskname))
                    RoleSetup.configure_disk(storagerouter_guid=storagerouter_guid,
                                             disk_guid=disk.guid,
                                             offset=partition.offset,
                                             size=disk.size,
                                             roles=[],
                                             api=api,
                                             partition_guid=partition.guid)
                    # Unmount partition
                    RoleRemover.LOGGER.info("Umounting disk {2}".format(partition.roles, partition.guid, diskname))
                    RoleRemover._umount(partition.mountpoint)
                    # Remove from fstab
                    RoleRemover.LOGGER.info("Removing {0} from fstab".format(partition.mountpoint, partition.guid, diskname))
                    FstabHelper().remove_by_mountpoint(partition.mountpoint)
                    # Remove filesystem
                    RoleRemover.LOGGER.info("Removing filesystem on partition {0} on disk {1}".format(partition.guid, diskname))
                    alias = partition.aliases[0]
                    device = '/dev/{0}'.format(diskname)
                    RoleRemover._remove_filesystem(device, alias)
                    # Remove partition from model
                    RoleRemover.LOGGER.info("Removing partition {0} on disk {1} from model".format(partition.guid, diskname))
                    partition.delete()
                else:
                    RoleRemover.LOGGER.info("Found no roles on partition {1} on disk {2}".format(partition.roles, partition.guid, diskname))
        else:
            RoleRemover.LOGGER.info("Found no partition on the disk.")
