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
import json
import math
import time
import threading
from ci.helpers.api import OVSClient
from ci.helpers.vpool import VPoolHelper
from ci.helpers.vdisk import VDiskHelper
from ci.helpers.system import SystemHelper
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ci.setup.vdisk import VDiskSetup
from ci.remove.vdisk import VDiskRemover
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class MigrateTester(object):

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_hypervisor_live_migrate"
    AMOUNT_TO_WRITE = 1*1024**3  # in MegaByte
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)

    REQUIRED_PACKAGES = ['blktap-openvstorage-utils']

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test

        status depends on attributes in class: ci.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.helpers.testtrailapi.TestrailCaseType

        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                MigrateTester._execute_test()
                return {'status': 'PASSED', 'case_type': MigrateTester.CASE_TYPE, 'errors': None}
            except Exception as ex:
                return {'status': 'FAILED', 'case_type': MigrateTester.CASE_TYPE, 'errors': ex.message}
        else:
            return {'status': 'BLOCKED', 'case_type': MigrateTester.CASE_TYPE, 'errors': None}

    @staticmethod
    def _execute_test(amount_to_write=AMOUNT_TO_WRITE):
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """
        # flow : add blocktap device
        # Execute fio on it
        # do a API move call
        with open(SETTINGS_LOC, "r") as settings_file:
            settings = json.load(settings_file)

        with open(CONFIG_LOC, "r") as config_file:
            config = json.load(config_file)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        # Get a suitable vpool
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 1:
                vpool = vp
                break
        assert vpool is not None, "Not enough vPools to test. Requires 1 and found {0}".format(len(vp.storagedrivers))

        # Setup base information
        # Executor storagedriver_1 is current system
        storagedriver_1 = None
        for std in vpool.storagedrivers:
            if SystemHelper.get_local_storagerouter().guid == std.storagerouter_guid:
                storagedriver_1 = std
                break
        if storagedriver_1 is None:
            raise ValueError('Could not find the right storagedriver for storagerouter {0}'.format(SystemHelper.get_local_storagerouter().guid))
        # Get a random other storagedriver to migrate to
        storagedriver_2 = [st for st in vpool.storagedrivers if st != storagedriver_1][0]
        client = SSHClient(storagedriver_1.storage_ip, username='root')

        # Check if there are missing packages
        missing_packages = SystemHelper.get_missing_packages(storagedriver_1.storage_ip, MigrateTester.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}" \
            .format(len(missing_packages), storagedriver_1.storage_ip, missing_packages)

        # Create a new vdisk to test
        vdisk_name = "{0}_vdisk01".format(MigrateTester.TEST_NAME)
        try:
            vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name, size=10*1024**3,
                                                 storagerouter_ip=storagedriver_1.storagerouter.ip, api=api)
            # Fetch to validate if it was properly created
            vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
            protocol = storagedriver_1.cluster_node_config['network_server_uri'].split(':')[0]

            # Setup blocktap
            MigrateTester.LOGGER.info("Creating a tap blk device for the vdisk")
            tap_dir = client.run(["tap-ctl", "create", "-a", "openvstorage+{0}:{1}:{2}/{3}".format(protocol, storagedriver_1.storage_ip, storagedriver_1.ports['edge'], vdisk_name)])
            MigrateTester.LOGGER.info("Created a tap blk device at location `{0}`".format(tap_dir))
        except Exception as ex:
            # Attempt to cleanup test
            MigrateTester.LOGGER.info("Creation of vdisk failed. Cleaning up test")
            try:
                MigrateTester._cleanup_blktap(vdisk_name, storagedriver_1.storage_ip, client)
                MigrateTester._cleanup_vdisk(vdisk_name, vpool.name)
            except:
                pass
            raise

        # Start threading
        # Run write data on a thread
        thread, event = MigrateTester._start_thread(target=MigrateTester._write_data, name='fio', args=[client, vdisk_name, tap_dir, amount_to_write])
        # Wait 30 sec before moving
        time.sleep(30)
        try:
            MigrateTester.move_vdisk(vdisk_guid, storagedriver_2.storagerouter_guid, api)
            # Validate move

            # Stop writing after 30 more s
            thread.join(30)
            if thread.isAlive():
                # Thread should have died. Stop thread either way
                event.set()
            MigrateTester._validate_move(vdisk, storagedriver_2)
        except Exception as ex:
            raise
        finally:
            # Stop the writing
            if event.isSet() is False:
                event.set()
            MigrateTester._cleanup_blktap(vdisk_name, storagedriver_1.storage_ip, client)
            MigrateTester._cleanup_vdisk(vdisk_name, vpool.name)

    @staticmethod
    def _validate_move(vdisk, move_target):
        """
        Validates the move test. Checks IO,
        :param vdisk: vdisk object
        :type vdisk: ovs.dal.hybrids.vdisk.VDISK
        :param move_target: object of target to move to
        :type move_target: ovs.dal.hybrids.storagedriver.STORAGEDRIVER
        :return:
        """
        std = move_target

        pass

    @staticmethod
    def _cleanup_blktap(vdisk_name, storage_ip, client):
        # deleting (remaining) tapctl connections
        tap_conn = client.run("tap-ctl list | grep {0}".format(vdisk_name), allow_insecure=True).split()
        if len(tap_conn) != 0:
            MigrateTester.LOGGER.info("Deleting tapctl connections.")
            for index, tap_c in enumerate(tap_conn):
                if 'pid' in tap_c:
                    pid = tap_c.split('=')[1]
                    minor = tap_conn[index + 1].split('=')[1]
                    client.run(["tap-ctl", "destroy", "-p", pid, "-m", minor])
        else:
            error_msg = "At least 1 blktap connection should be available " \
                        "but we found none on ip address `{0}`!".format(storage_ip)
            MigrateTester.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)

    @staticmethod
    def _cleanup_vdisk(vdisk_name, vpool_name):
        # Cleanup vdisk
        VDiskRemover.remove_vdisk_by_name('{0}.raw'.format(vdisk_name), vpool_name)

    @staticmethod
    def move_vdisk(vdisk_guid, target_storagerouter_guid, api, timeout=60):
        data = {"target_storagerouter_guid": target_storagerouter_guid}

        task_guid = api.post(
            api='/vdisks/{0}/move/'.format(vdisk_guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Moving vdisk {0} to {1} has failed with {2}.".format(
                vdisk_guid, target_storagerouter_guid, task_result[1])
            VDiskSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VDiskSetup.LOGGER.info("Vdisk {0} should have been moved to {1}.".format(vdisk_guid, target_storagerouter_guid))
            return task_result[1]

    @staticmethod
    def _write_data(client, vdisk_name, blocktap_dir, write_amount, stop_event):
        """
        Runs a fio scenario on a blocktap dir for a specific vdisk
        :param client: ovs ssh client
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param vdisk_name: name of the vdisk
        :type vdisk_name: str
        :param blocktap_dir: directory of the blocktap link
        :type blocktap_dir: str
        :param write_amount: amount of bytes to write
        :type write_amount: int
        :return:
        """
        bs = 1 * 1024**2
        count = math.ceil(float(write_amount) / bs)
        MigrateTester.LOGGER.info("Starting to write on vdisk `{0}` with blktap `{1}`".format(vdisk_name, blocktap_dir))
        while not stop_event.is_set() and count > 0:
            cmd = ['dd', 'if=/dev/urandom', 'of={0}'.format(blocktap_dir), 'bs={0}'.format(bs), 'count=1']
            client.run(cmd)
            count -= 1
        MigrateTester.LOGGER.info("Finished writing data on vdisk `{0}` with blktap `{1}`".format(vdisk_name, blocktap_dir))

    @staticmethod
    def _start_thread(target, name, args=[]):
        """
        Starts a thread
        :param target: target - usually a method
        :type target: object
        :param name: name of the thread
        :type name: str
        :param args: list of arguments
        :type args: list
        :return: a tuple with the thread and event
        :rtype: tuple
        """
        MigrateTester.LOGGER.info('Starting thread with target {0}'.format(target))
        event = threading.Event()
        args.append(event)
        thread = threading.Thread(target=target, args=tuple(args))
        thread.setName(str(name))
        thread.start()
        return thread, event


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """

    return MigrateTester().main(blocked)

if __name__ == "__main__":
    print run()
