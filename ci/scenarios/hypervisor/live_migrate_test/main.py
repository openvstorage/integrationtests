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
import socket
import threading
import subprocess
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
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class MigrateTester(object):
    """
    @TODO remove IP dependency of VM
    Requirements to run this test:
    QEMU user should be root (user = "root" and group = "root" in /etc/libvirt/qemu.conf)
    Both QEMU hosts should have a br1 bridge interface
    The prepared image has to be present (see settings.json)
    This test will create a new VM, set its disk protocol to ovs and start a fio test on it.
    After 30s the VM will migrate to a different host.
    Both IOPS and DAL will be checked afterwards.
    """
    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_hypervisor_live_migrate"
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)
    SLEEP_TIME = 30
    REQUIRED_PACKAGES = ["qemu-kvm", "libvirt0", "python-libvirt", "virtinst", "genisoimage"]
    # RW mixes for Fio, bs for dd
    DATA_TEST_CASES = {
        'fio': [(0, 100), (30, 70), (40, 60), (50, 50), (70, 30), (100, 0)]
    }
    VM_NAME = 'migrate-test'
    VM_WAIT_TIME = 300  # wait time before timing out on the vm install in seconds
    VM_CREATION_MESSAGE = "I am created!"
    CLOUD_INIT_DATA = {
        "script_loc": "https://raw.githubusercontent.com/kinvaris/cloud-init/master/create-config-drive",
        "script_dest": "/tmp/cloud_init_script.sh",
        "user-data_loc": "/tmp/user-data-migrate-test",
        "config_dest": "/tmp/cloud-init-config-migrate-test"
    }
    AMOUNT_TO_WRITE = 10 * 1024 ** 3  # in MegaByte

    VM_USERNAME = "root"
    VM_PASSWORD = "rooter"

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
    def _execute_test():
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """

        # ---------------
        # Validation
        # ---------------
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
        d_client = SSHClient(storagedriver_2.storage_ip, username='root')
        # check if enough images available
        image_path = settings['images'].get("migrate-test").get("image_path")
        assert image_path is not None, "Fio-test image not set in `{0}`".format(SETTINGS_LOC)

        # check if image exists
        assert client.file_exists(image_path), "Image `{0}` does not exists on `{1}`!".format(image_path,
                                                                                              storagedriver_1.storage_ip)
        # Check if there are missing packages
        missing_packages = SystemHelper.get_missing_packages(storagedriver_1.storage_ip, MigrateTester.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}".format(len(missing_packages), storagedriver_1.storage_ip, missing_packages)

        # Get the cloud init file
        cloud_init_loc = MigrateTester.CLOUD_INIT_DATA.get("script_dest")
        client.run(["wget",
                    MigrateTester.CLOUD_INIT_DATA.get("script_loc"),
                    "-O",
                    cloud_init_loc])
        client.file_chmod(cloud_init_loc, 755)
        assert client.file_exists(cloud_init_loc), "Could not fetch the cloud init script"
        # ---------------
        # Start testing
        # ---------------
        # Cache to validate properties
        values_to_check = {
            'source_std': storagedriver_1.serialize(),
            'target_std': storagedriver_2.serialize()
        }
        # Set some values
        # Create a new vdisk to test
        vdisk_name = "{0}_vdisk01".format(MigrateTester.TEST_NAME)
        vdisk_path = "/mnt/{0}/{1}.raw".format(vpool.name, vdisk_name)
        protocol = storagedriver_1.cluster_node_config['network_server_uri'].split(':')[0]

        hypervisor = HypervisorFactory.get(storagedriver_1.storage_ip, 'root', 'rooter', 'KVM')
        d_hypervisor = HypervisorFactory.get(storagedriver_2.storage_ip, "root", "rooter", "KVM")
        disks = [{
            'mountpoint': vdisk_path,
        }]
        networks = [{
            'network': 'default',
            'mac': 'RANDOM',
            'model': 'e1000',
        }]
        # Milestones in the code
        iso_loc = None
        test_prepared = False
        files_generated = False
        vm_created = False
        migrated = False
        # Copy the Ubuntu img
        try:
            try:
                MigrateTester.LOGGER.info('Copying the image to the vdisk.')
                client.run(['qemu-img', 'convert', image_path, 'openvstorage+{0}:{1}:{2}/{3}'
                           .format(protocol, storagedriver_1.storage_ip, storagedriver_1.ports['edge'], vdisk_name)])
                # Fetch to validate if it was properly created
            except RuntimeError as ex:
                MigrateTester.LOGGER.error("Could not covert the image. Got {0}".format(str(ex)))
                raise
            vdisk = VDiskHelper.get_vdisk_by_name(vdisk_path.rsplit('/', 1)[1], vpool.name)

            # # Snapshot to revert back to after every migrate scenario
            snapshot_guid = VDiskSetup.create_snapshot(MigrateTester.TEST_NAME, vdisk.devicename, vpool.name, api,
                                                       consistent=False)
            test_prepared = MigrateTester._prepare_migrate([client, d_client], MigrateTester.VM_NAME)
            for cmd_type, configurations in MigrateTester.DATA_TEST_CASES.iteritems():
                for configuration in configurations:
                    try:
                        # Certain milestones should be reset for every run
                        files_generated = False
                        iso_loc = None
                        files_generated = False
                        vm_created = False
                        migrated = False
                        # Keep track of the current state of the vdisk
                        values_to_check['vdisk'] = vdisk.serialize()
                        try:
                            # Revert back to snapshot
                            VDiskSetup.rollback_to_snapshot(vdisk_name=vdisk.devicename,
                                                            vpool_name=vpool.name,
                                                            snapshot_id=snapshot_guid,
                                                            api=api)
                        except RuntimeError as ex:
                            MigrateTester.LOGGER.error("Rolling back to snapshot has failed. Got {0}".format(str(ex)))
                            raise
                        # Initialize listener for VM installation
                        listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        MigrateTester.LOGGER.info("Socket created.")
                        # Bind to first available port
                        try:
                            listening_socket.bind((storagedriver_1.storage_ip, 0))
                        except socket.error as ex:
                            MigrateTester.LOGGER.error("Could not bind the socket. Got {0}".format(str(ex)))
                            raise
                        port = listening_socket.getsockname()[1]
                        listening_socket.listen(1)
                        try:
                            # convert prepped iso
                            iso_loc = MigrateTester._generate_cloud_init(client=client,
                                                                         convert_script_loc=cloud_init_loc,
                                                                         port=port,
                                                                         hypervisor_ip=storagedriver_1.storage_ip)
                            files_generated = True
                            client.run(['qemu-img', 'convert', iso_loc, 'openvstorage+{0}:{1}:{2}/{3}'
                                       .format(protocol, storagedriver_1.storage_ip, storagedriver_1.ports['edge'],
                                               iso_loc.rsplit('/', 1)[1])])
                            cd_path = "/mnt/{0}/{1}.raw".format(vpool.name, iso_loc.rsplit('/', 1)[1])
                        except Exception as ex:
                            MigrateTester.LOGGER.error("Could not setup cloud init files. Got {0}".format(str(ex)))
                            raise
                        try:
                            # Setup VM
                            MigrateTester.LOGGER.info('Creating VM {0} with image as disk'.format(MigrateTester.VM_NAME))
                            hypervisor.sdk.create_vm(MigrateTester.VM_NAME,
                                                     vcpus=2,
                                                     ram=1024,
                                                     cdrom_iso=cd_path,
                                                     disks=disks,
                                                     networks=networks,
                                                     ovs_vm=True,
                                                     hostname=MigrateTester.VM_NAME,
                                                     edge_port=storagedriver_1.ports['edge'],
                                                     start=True)
                            vm_created = True
                            MigrateTester.LOGGER.info('Created VM {0}.'.format(MigrateTester.VM_NAME))
                        except RuntimeError as ex:
                            MigrateTester.LOGGER.error("Creation of VM failed.")
                            raise
                        # Wait for input from the VM for max x seconds
                        client_connected = False
                        start_time = datetime.now()
                        vm_ip = None
                        try:
                            while not client_connected and (start_time-datetime.now()).total_seconds() < MigrateTester.VM_WAIT_TIME:
                                conn, addr = listening_socket.accept()
                                vm_ip = addr[0]
                                MigrateTester.LOGGER.info("Connected with {0}:{1}".format(addr[0], addr[1]))
                                data = conn.recv(1024)
                                if data == MigrateTester.VM_CREATION_MESSAGE:
                                    client_connected = True
                        except:
                            raise
                        finally:
                            listening_socket.close()
                        if vm_ip is None or vm_ip not in hypervisor.sdk.get_guest_ip_addresses(MigrateTester.VM_NAME):
                            raise RuntimeError("The VM did not connect to the hypervisor. "
                                               "Hypervisor has leased {0} and got {1}"
                                               .format(hypervisor.sdk.get_guest_ip_addresses(MigrateTester.VM_NAME), vm_ip))
                        vm_client = SSHClient(vm_ip, MigrateTester.VM_USERNAME, MigrateTester.VM_PASSWORD)
                        MigrateTester.LOGGER.info("Connection was established with the VM.")
                        MigrateTester.LOGGER.info("Installing fio on the VM.")
                        vm_client.run(["apt-get", "install", "fio", "-y", "--force-yes"])
                        # Start threading - own try except to kill off rogue threads
                        try:
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
                            try:
                                threads.append(MigrateTester._start_thread(MigrateTester._check_downtimes, name='iops',
                                                                           args=[iops_activity, vdisk]))
                                MigrateTester._write_data(vm_client, cmd_type, configuration)
                            except Exception as ex:
                                MigrateTester.LOGGER.error("Could not start threading. Got {0}".format(str(ex)))
                                raise
                            time.sleep(MigrateTester.SLEEP_TIME)
                            try:
                                MigrateTester.LOGGER.info("Migrating VM.")
                                MigrateTester.migrate(hypervisor=hypervisor,
                                                      d_ip=storagedriver_2.storage_ip,
                                                      d_login=config['ci']['user']['shell']['username'],
                                                      vmid=MigrateTester.VM_NAME)
                                migrated = True
                            except Exception as ex:
                                MigrateTester.LOGGER.error('Failed to migrate. Got {2}'.format(cmd_type, configuration, str(ex)))
                                raise
                            # Stop writing after 30 more s
                            MigrateTester.LOGGER.info('Writing and monitoring for another {0}s.'.format(MigrateTester.SLEEP_TIME))
                            time.sleep(MigrateTester.SLEEP_TIME)
                            # Stop IO
                            for thread_pair in threads:
                                if thread_pair[0].isAlive():
                                    thread_pair[1].set()
                            # Wait for threads to die
                            for thread_pair in threads:
                                thread_pair[0].join()
                            MigrateTester.LOGGER.info('IOPS monitoring: {0}'.format(iops_activity))
                            # Validate move
                            MigrateTester._validate_move(values_to_check)

                            # Validate downtime
                            # Each log means +-4s downtime and slept twice
                            if len(iops_activity["down"]) * 4 >= MigrateTester.SLEEP_TIME * 2:
                                raise ValueError("Thread did not cause any IOPS to happen.")
                        except Exception:
                            MigrateTester.LOGGER.error('Error occurred scenario: read: {0}, write {1}.'.format(configuration[0], configuration[1]))
                            raise
                        finally:
                            # Stop all threads
                            for thread_pair in threads:
                                if thread_pair[1].isSet() is False:
                                    thread_pair[1].set()
                            # Wait for threads to die
                            for thread_pair in threads:
                                thread_pair[0].join()
                    except Exception:
                        raise
                    finally:
                        if vm_created is True:
                            MigrateTester._cleanup_vm(hypervisor, MigrateTester.VM_NAME, False)
                        if iso_loc is not None:
                            MigrateTester._cleanup_vdisk(iso_loc.rsplit('/', 1)[1], vpool.name, False)
                        if migrated is True:
                            MigrateTester._cleanup_vm(d_hypervisor, MigrateTester.VM_NAME, False)
        except Exception as ex:
            MigrateTester.LOGGER.exception('Live migrate test failed. Got {0}'.format(str(ex)))
            raise
        finally:
            # Always cleanup the vdisk after all tests have run or error occured
            try:
                if test_prepared is True:
                    MigrateTester._cleanup_preparation([client, d_client])
                if files_generated is True:
                    MigrateTester._cleanup_generated_files(client)
                MigrateTester._cleanup_vdisk(vdisk_name, vpool.name, False)
            except Exception:
                pass
            raise

    @staticmethod
    def migrate(hypervisor, d_ip, d_login, vmid):
        """
        Migrates a VM between hypervisors
        :param hypervisor: hypervisor instance
        :param d_ip: destination ip
        :param d_login: destination loign
        :param vmid: vm identifier
        :return:
        """
        # Migrate VM
        hypervisor.sdk.migrate(vmid, d_ip, d_login)

    @staticmethod
    def _prepare_migrate(clients, hostname):
        """
        Sets up everything to ensure that migrate will be succesful
        :param clients: sshclients of the all hosts that will be migrated too
        :param hostname: hostname that was specified in the creation of the vm
        :return:
        """
        for client in clients:
            # Append the hostname record to /etc/hosts
            cmd = "echo {0} {1} >> /etc/hosts".format(client.ip, hostname)
            client.run(cmd, allow_insecure=True)
        return True

    @staticmethod
    def _cleanup_preparation(clients):
        """
        Cleanups all preps made to do migration
        :param clients: sshclients of the all hosts that will be migrated too
        :return:
        """
        for client in clients:
            cmd = "head -n -1 /etc/hosts > /etc/hosts~ ; mv /etc/hosts~ /etc/hosts"
            client.run(cmd, allow_insecure=True)

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
    def _cleanup_vm(hypervisor, vmid, blocking=True):
        """
        Cleans up the created virtual machine
        :param hypervisor: hypervisor instance
        :param vmid: vm identifier
        :param blocking: boolean to determine whether errors should raise or not
        :return:
        """
        try:
            hypervisor.sdk.delete_vm(vmid=vmid, delete_disks=False)
        except Exception as ex:
            MigrateTester.LOGGER.error(str(ex))
            if blocking is True:
                raise
            else:
                pass

    @staticmethod
    def _cleanup_generated_files(client):
        """
        Cleans up generated files
        :param client: ovs ssh client for current node
        :type client: ovs.extensions.generic.sshclient.SSHClient
        """
        for key, value in MigrateTester.CLOUD_INIT_DATA.iteritems():
            MigrateTester.LOGGER.info("Deleting {0}".format(value))
            client.file_delete(value)
        return True

    @staticmethod
    def _generate_cloud_init(client, convert_script_loc, port, hypervisor_ip, username="test", passwd="test"):
        """
        Runs a dd on a blocktap dir for a specific vdisk
        :param client: ovs ssh client for current node
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param username: username of the user that will be added to the vm
        :type username: str
        :param passwd: password of the user that will be added to the vm
        :type passwd: str
        :param convert_script_loc: location to the conversion script
        :type convert_script_loc: str
        :return:
        """
        path = MigrateTester.CLOUD_INIT_DATA.get("user-data_loc")
        # write out user-data
        lines = [
            '#!/bin/bash\n',
            '#user conf',
            'sudo echo "root:rooter" | chpasswd',
            'sudo useradd {0}'.format(username),
            'sudo echo "{0}:{1}" | chpasswd'.format(username, passwd),
            'sudo adduser {0} sudo\n'.format(username),
            'apt-get update',
            'sed -ie "s/PermitRootLogin prohibit-password/PermitRootLogin yes/" /etc/ssh/sshd_config',
            'sed -ie "s/PasswordAuthentication no/PasswordAuthentication yes/" /etc/ssh/sshd_config',
            'sudo service ssh restart',
            'echo -n {0} | netcat -w 0 {1} {2}'.format(MigrateTester.VM_CREATION_MESSAGE, hypervisor_ip, port)

        ]
        with open(path, 'w') as user_data_file:
            user_data_file.write('\n'.join(lines))
        client.file_upload(path, path)
        # run script that generates meta-data and parser user-data and meta-data to a iso

        convert_cmd = [convert_script_loc,
                       "--user-data",
                       path,
                       MigrateTester.CLOUD_INIT_DATA.get("config_dest")]
        try:
            client.run(convert_cmd)
            return MigrateTester.CLOUD_INIT_DATA.get("config_dest")
        except subprocess.CalledProcessError as ex:
            MigrateTester.LOGGER.error("Could not generate the cloud init file. Got '{0}' during iso conversion."
                                       .format(str(ex.output)))
            raise

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
    def _write_data(client, cmd_type, configuration):
        """
        Fire and forget an IO test
        Starts a screen session detaches the sshclient
        :param client: ovs ssh client for the vm
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :return:
        """

        bs = 1 * 1024 ** 2
        write_size = 10 * 1024 ** 2
        MigrateTester.LOGGER.info("Starting to write on VM `{0}`".format(client.ip))
        if cmd_type == 'fio':
            cmd = ["fio", "--name=test", "--ioengine=libaio", "--iodepth=4",
                   "--rw=readwrite", "--bs={0}".format(bs), "--direct=1", "--size={0}".format(write_size),
                   "--rwmixread={0}".format(configuration[0]), "--rwmixwrite={0}".format(configuration[1])]
            cmd = "screen -S fio -dm bash -c 'while true; do {0}; done'".format(' '.join(cmd))
        else:
            raise ValueError('{0} is not supported for writing data.'.format(cmd_type))
        MigrateTester.LOGGER.info("Writing data with: {0}".format(cmd))
        client.run(cmd, allow_insecure=True)

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
