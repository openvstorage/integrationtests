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
import subprocess
import paramiko
from datetime import datetime
from ci.helpers.api import OVSClient
from ci.helpers.hypervisor.hypervisor import HypervisorFactory
from ci.helpers.vpool import VPoolHelper
from ci.helpers.vdisk import VDiskHelper
from ci.helpers.storagedriver import StoragedriverHelper
from ci.helpers.system import SystemHelper
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ci.setup.vdisk import VDiskSetup
from ci.remove.vdisk import VDiskRemover
from ovs.extensions.generic.sshclient import SSHClient, UnableToConnectException
from ovs.log.log_handler import LogHandler


class MigrateTester(object):
    """
    Requirements to run this test:
    QEMU user should be root (user = "root" and group = "root" in /etc/libvirt/qemu.conf)
    Both QEMU hosts should have a br1 bridge interface
    The prepared image has to be present (see settings.json)
    The network must be set to a bridged interface
    This test will create a new VM, set its disk protocol to ovs and start a fio test on it.
    After 30s the VM will migrate to a different host.
    Both IOPS and DAL will be checked afterwards.
    """
    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_hypervisor_live_migrate"
    AMOUNT_TO_WRITE = 1 * 1024 ** 3  # in MegaByte
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)
    SLEEP_TIME = 30
    REQUIRED_PACKAGES = ["qemu-kvm", "libvirt0", "python-libvirt", "virtinst"]
    # RW mixes for Fio, bs for dd
    DATA_TEST_CASES = {
        'fio': [(0, 100), (30, 70), (40, 60), (50, 50), (70, 30), (100, 0)]
    }
    BRIDGE_INTERFACE = "br0"
    VM_NAME = 'migrate-test'
    VM_USERNAME = "root"
    VM_PASSWORD = "rooter"
    VM_CONNECTION_RETRIES = 5
    VM_CONNECTION_RETRY_DELAY = 60

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
                return {'status': 'FAILED', 'case_type': MigrateTester.CASE_TYPE, 'errors': str(ex)}
        else:
            return {'status': 'BLOCKED', 'case_type': MigrateTester.CASE_TYPE, 'errors': None}

    @staticmethod
    def _execute_test(amount_to_write=AMOUNT_TO_WRITE):
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """
        with open(CONFIG_LOC, "r") as config_file:
            config = json.load(config_file)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        with open(SETTINGS_LOC, "r") as JSON_SETTINGS:
            settings = json.load(JSON_SETTINGS)

        # Get a suitable vpool
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 1:
                vpool = vp
                break
        assert vpool is not None, "Not enough vPools to test. Requires 1 and found 0."

        # Setup base information
        # Executor storagedriver_1 is current system
        storagedriver_1 = None
        for std in vpool.storagedrivers:
            if SystemHelper.get_local_storagerouter().guid == std.storagerouter_guid:
                storagedriver_1 = std
                break

        assert storagedriver_1 is not None, 'Could not find the right storagedriver for storagerouter {0}'.format(SystemHelper.get_local_storagerouter().guid)
        # Get a random other storagedriver to migrate to
        other_stds = [st for st in vpool.storagedrivers if st != storagedriver_1]
        assert len(other_stds) >= 1, 'Only found one storagedriver for vpool {0}. This tests requires at least 2.'.format(vpool.name)
        storagedriver_2 = [st for st in vpool.storagedrivers if st != storagedriver_1][0]

        client = SSHClient(storagedriver_1.storage_ip, username='root')

        # check if enough images available
        images = settings['images']
        image_path = images.get("migrate-test").get("path")
        assert image_path is not None, "Fio-test image not set in `{0}`".format(SETTINGS_LOC)

        # check if image exists
        assert client.file_exists(image_path), "Image `{0}` does not exists on `{1}`!".format(image_path,
                                                                                              storagedriver_1.storage_ip)

        # Cache to validate properties
        values_to_check = {
            'source_std': storagedriver_1.serialize(),
            'target_std': storagedriver_2.serialize()
        }

        # Check if there are missing packages
        missing_packages = SystemHelper.get_missing_packages(storagedriver_1.storage_ip, MigrateTester.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}".format(len(missing_packages), storagedriver_1.storage_ip, missing_packages)

        # Set some values
        # Create a new vdisk to test
        vdisk_name = "{0}_vdisk01".format(MigrateTester.TEST_NAME)
        storage_ip = storagedriver_1.storage_ip
        edge_port = storagedriver_1.ports['edge']
        vdisk_path = "/mnt/{0}/{1}.raw".format(vpool.name, vdisk_name)

        hypervisor = HypervisorFactory.get(client.ip, 'root', 'rooter', 'KVM')
        d_hypervisor = HypervisorFactory.get(storagedriver_2.storage_ip, "root", "rooter", "KVM")
        disks = [{
            'mountpoint': vdisk_path,
        }]
        networks = [{
            'bridge': MigrateTester.BRIDGE_INTERFACE,
            'mac': 'RANDOM',
            'model': 'e1000',
        }]
        # Setup clean install with fio
        vdisk_guid = VDiskSetup.create_vdisk(vdisk_name='{}.raw'.format(vdisk_name),
                                             vpool_name=vpool.name,
                                             size=10 * 1024 ** 3,
                                             storagerouter_ip=storagedriver_1.storagerouter.ip,
                                             api=api)
        MigrateTester.LOGGER.info("Copying the image to the vdisk.")
        client.run(["dd", "if={0}".format(image_path),
                    "of={0}".format(vdisk_path),
                    "bs=256K",
                    "conv=notrunc"])
        # Fetch to validate if it was properly created
        vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)

        # Snapshot to revert back to after every migrate scenario
        snapshot_guid = VDiskSetup.create_snapshot(MigrateTester.TEST_NAME, vdisk.devicename, vpool.name, api, consistent=False)
        try:
            for cmd_type, configurations in MigrateTester.DATA_TEST_CASES.iteritems():
                for configuration in configurations:
                    try:
                        # Revert back to snapshot
                        VDiskSetup.rollback_to_snapshot(vdisk_name= vdisk.devicename, vpool_name=vpool.name, snapshot_id=snapshot_guid, api=api)
                        values_to_check['vdisk'] = vdisk.serialize()
                        # Setup VM
                        MigrateTester.LOGGER.info('Creating VM {0} with image as disk'.format(MigrateTester.VM_NAME))
                        hypervisor.sdk.create_vm(MigrateTester.VM_NAME, vcpus=2, ram=1024, disks=disks, networks=networks,
                                                 ovs_vm=False, storagerouter_ip=storage_ip, edge_port=edge_port, start=True)
                        MigrateTester.LOGGER.info('Created VM {0}.'.format(MigrateTester.VM_NAME))
                        # Could be that the VM does not respond instantly
                        retries = 0
                        vm_client = None
                        while retries <= MigrateTester.VM_CONNECTION_RETRIES and vm_client is None:
                            try:
                                vm_client = SSHClient(images.get("migrate-test").get("ip"), MigrateTester.VM_USERNAME,
                                                      MigrateTester.VM_PASSWORD)
                            except (UnableToConnectException, paramiko.SSHException) as ex:
                                MigrateTester.LOGGER.warning("Could not connect to VM on retry {0}. Waiting for {1}s"
                                                             .format(retries, MigrateTester.VM_CONNECTION_RETRY_DELAY))
                                retries += 1
                                time.sleep(MigrateTester.VM_CONNECTION_RETRY_DELAY)
                        if vm_client is None:
                            raise RuntimeError("Could not establish a connection to the VM.")
                        else:
                            MigrateTester.LOGGER.info("Connection was established with the VM.")
                    except Exception as ex:
                        # Attempt to cleanup test
                        if isinstance(ex, subprocess.CalledProcessError):
                            MigrateTester.LOGGER.error("Could not copy the image.")
                        if isinstance(ex, RuntimeError):
                            MigrateTester.LOGGER.error("Creation of VM failed. Cleaning up test")
                        if isinstance(ex, UnableToConnectException):
                            MigrateTester.LOGGER.error("Could not connect to the VM after {0}s."
                                                       .format(MigrateTester.VM_CONNECTION_RETRY_DELAY * MigrateTester.VM_CONNECTION_RETRIES))
                        raise

                    # Start threading
                    threads = []
                    # Monitor IOPS activity
                    iops_activity = {
                        "down": [],
                        "descending": [],
                        "rising": [],
                        "highest": None,
                        "lowest": None
                    }
                    MigrateTester.LOGGER.info("Starting threads.")
                    threads.append(MigrateTester._start_thread(MigrateTester._check_downtimes, name='iops',
                                                               args=[iops_activity, vdisk]))
                    # Run write data on a thread
                    threads.append(MigrateTester._start_thread(target=MigrateTester._write_data,
                                                               name='fio',
                                                               args=[vm_client,
                                                                     amount_to_write,
                                                                     cmd_type,
                                                                     configuration]))
                    time.sleep(MigrateTester.SLEEP_TIME)
                    try:
                        MigrateTester.LOGGER.info("Migrating VM.")
                        MigrateTester.migrate(hypervisor=hypervisor,
                                              d_ip=storagedriver_2.storage_ip,
                                              d_login=config['ci']['user']['shell']['username'],
                                              vmid=MigrateTester.VM_NAME)
                        # Stop writing after 30 more s
                        MigrateTester.LOGGER.info('Writing and monitoring for another {0}s.'.format(MigrateTester.SLEEP_TIME))
                        time.sleep(MigrateTester.SLEEP_TIME)
                        # Validate move
                        MigrateTester._validate_move(values_to_check)
                        # Stop IO
                        for thread_pair in threads:
                            if thread_pair[0].isAlive():
                                thread_pair[1].set()
                        # Sleep to let the threads die
                        time.sleep(5)
                        MigrateTester.LOGGER.info('IOPS monitoring: {0}'.format(iops_activity))
                        # Validate downtime
                        # Each log means +-4s downtime and slept twice
                        if len(iops_activity["down"]) * 4 >= MigrateTester.SLEEP_TIME * 2:
                            raise ValueError("Thread did not cause any IOPS to happen.")
                    except Exception as ex:
                        MigrateTester.LOGGER.error('Failed during {0} with configuration {1}'.format(cmd_type, configuration))
                        raise
                    finally:
                        # Stop all threads
                        for thread_pair in threads:
                            if thread_pair[1].isSet():
                                thread_pair[1].set()
                        MigrateTester._cleanup_vm([hypervisor, d_hypervisor], MigrateTester.VM_NAME, False)
        except Exception as ex:
            raise
        finally:
            # Always cleanup the vdisk after all tests have run or error occured
            try:
                MigrateTester._cleanup_vm([hypervisor, d_hypervisor], MigrateTester.VM_NAME, False)
                MigrateTester._cleanup_vdisk(vdisk_name, vpool.name, False)
            except:
                pass
            raise

    @staticmethod
    def migrate(hypervisor, d_ip, d_login, vmid):
        """
        Migrates a VM between hypervisors
        :return:
        """
        # Migrate VM
        hypervisor.sdk.migrate(vmid, d_ip, d_login)

    @staticmethod
    def _validate_move(values_to_check):
        """
        Validates the move test. Checks IO, and checks for dal changes
        :param values_to_check: dict with values to validate if they updated
        :type values_to_check: dict
        :return:
        """
        # Fetch dal object
        source_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['source_std']['guid'])
        target_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['target_std']['guid'])
        try:
            MigrateTester._validate_dal(values_to_check)
        except ValueError as ex:
            MigrateTester.LOGGER.warning('DAL did not automatically change after a move. Should be reported to engineers. Got {0}'.format(ex))
            source_std.invalidate_dynamics([])
            target_std.invalidate_dynamics([])
            # Properties should have been reloaded
            values_to_check['source_std'] = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['source_std']['guid']).serialize()
            values_to_check['target_std'] = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['target_std']['guid']).serialize()
            MigrateTester._validate_dal(values_to_check)

    @staticmethod
    def _validate_dal(values):
        """
        Validates the move test. Checks for dal changes
        :param values: dict with values to validate if they updated
        :type values: dict
        :return:
        """
        # Fetch them from the dal
        source_std = StoragedriverHelper.get_storagedriver_by_guid(values['source_std']['guid'])
        target_std = StoragedriverHelper.get_storagedriver_by_guid(values['target_std']['guid'])
        vdisk = VDiskHelper.get_vdisk_by_guid(values['vdisk']['guid'])
        if values['source_std'] == source_std.serialize():
            # DAL values did not update - expecting a change in vdisks_guids
            raise ValueError('Expecting changes in the target Storagedriver but nothing changed.')
        else:
            # Expecting changes in vdisks_guids
            if vdisk.guid in source_std.vdisks_guids:
                raise ValueError('Vdisks guids were not updated after move for source storagedriver.')
            else:
                MigrateTester.LOGGER.info('All properties are updated for source storagedriver.')
        if values['target_std'] == target_std.serialize():
            raise ValueError('Expecting changes in the target Storagedriver but nothing changed.')
        else:
            if vdisk.guid not in target_std.vdisks_guids:
                raise ValueError('Vdisks guids were not updated after move for target storagedriver.')
            else:
                MigrateTester.LOGGER.info('All properties are updated for target storagedriver.')
        if values["vdisk"] == vdisk.serialize():
            raise ValueError('Expecting changes in the vdisk but nothing changed.')
        else:
            if vdisk.storagerouter_guid == target_std.storagerouter.guid:
                MigrateTester.LOGGER.info('All properties are updated for vdisk.')
            else:
                ValueError('Expected {0} but found {1} for vdisk.storagerouter_guid'.format(vdisk.storagerouter_guid, vdisk.storagerouter_guid))
        MigrateTester.LOGGER.info('Move vdisk was successful according to the dal (which fetches volumedriver info).')

    @staticmethod
    def _cleanup_vdisk(vdisk_name, vpool_name, blocking=True):
        """
        Attempt to cleanup vdisk
        :param vdisk_name: name of the vdisk
        :param vpool_name: name of the vpool
        :param blocking: boolean to determine whether errors should raise or not
        :return:
        """
        # Cleanup vdisk
        try:
            VDiskRemover.remove_vdisk_by_name('{0}.raw'.format(vdisk_name), vpool_name)
        except Exception as ex:
            MigrateTester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _cleanup_vm(hypervisors, vmid, blocking=True):
        """
        Cleans up the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :return:
        """
        for hypervisor in hypervisors:
            try:
                hypervisor.sdk.delete_vm(vmid=vmid, delete_disks=False)
            except Exception as ex:
                MigrateTester.LOGGER.error(str(ex))
                if blocking is True:
                    raise
                else:
                    pass

    @staticmethod
    def _write_data(client, write_amount, cmd_type, configuration, stop_event):
        """
        Runs a dd on a blocktap dir for a specific vdisk
        :param client: ovs ssh client for the vm
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param write_amount: amount of bytes to write
        :type write_amount: int
        :param stop_event: Threading event to watch for
        :type stop_event: threading._Event
        :return:
        """

        bs = 1 * 1024**2
        write_size = 10 * 1024**2
        count = int(math.ceil(write_size / bs))
        iterations = math.ceil(float(write_amount) / write_size)
        MigrateTester.LOGGER.info("Starting to write on VM `{0}`".format(client.ip))
        if cmd_type == 'fio':
            cmd = ["fio", "--name=test", "--ioengine=libaio", "--iodepth=4",
                   "--rw=readwrite", "--bs={0}".format(bs), "--direct=1", "--size={0}".format(write_size),
                   "--rwmixread={0}".format(configuration[0]), "--rwmixwrite={0}".format(configuration[1])]
        else:
            raise ValueError('{0} is not supported for writing data.'.format(cmd_type))
        MigrateTester.LOGGER.info("Writing data with: {0}".format(" ".join(cmd)))
        while not stop_event.is_set() and iterations > 0:
            client.run(cmd)
            iterations -= 1
        MigrateTester.LOGGER.info("Finished writing data on VM `{0}`".format(client.ip))

    @staticmethod
    def _check_downtimes(results, vdisk, stop_event):
        """
        Threading method that will check for IOPS downtimes
        :param results: variable reserved for this thread
        :type results: dict
        :param vdisk: vdisk object
        :type vdisk: ovs.dal.hybrids.vdisk.VDISK
        :param stop_event: Threading event to watch for
        :type stop_event: threading._Event
        :return:
        """
        last_recorded_iops = None
        while not stop_event.is_set():
            now = datetime.today().strftime("%Y-%m-%d %H:%M:%S")
            current_iops = vdisk.statistics['operations']
            if current_iops == 0:
                results["down"].append((now, current_iops))
            else:
                if last_recorded_iops >= current_iops:
                    results["rising"].append((now, current_iops))
                else:
                    results["descending"].append((now, current_iops))
                if current_iops > results['highest'] or results['highest'] is None:
                    results['highest'] = current_iops
                if current_iops < results['lowest'] or results['lowest'] is None:
                    results['lowest'] = current_iops
            # Sleep to avoid caching
            last_recorded_iops = current_iops
            time.sleep(4)

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
