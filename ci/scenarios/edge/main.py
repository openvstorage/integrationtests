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
import random
from datetime import datetime
from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.thread import ThreadHelper, Waiter
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.helpers.storagedriver import StoragedriverHelper
from ci.autotests import gather_results
from ci.main import CONFIG_LOC
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.packages.package import PackageManager
from ovs.extensions.services.service import ServiceManager
from ovs.log.log_handler import LogHandler


class EdgeTester(object):
    """
    Test the edge magic
    """
    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_edge_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)

    CLOUD_INIT_DATA = {
        'script_loc': 'https://raw.githubusercontent.com/kinvaris/cloud-init/master/create-config-drive',
        'script_dest': '/tmp/cloud_init_script.sh',
        'user-data_loc': '/tmp/user-data-migrate-test',
        'config_dest': '/tmp/cloud-init-config-migrate-test'
    }
    # DATA_TEST_CASES = [(0, 100), (30, 70), (40, 60), (50, 50), (70, 30), (100, 0)]  # read write patterns to test (read, write)
    DATA_TEST_CASES = [(100, 0)]
    VDISK_THREAD_LIMIT = 5  # Each monitor thread queries x amount of vdisks
    FIO_VDISK_LIMIT = 50  # Each fio uses x disks
    IO_REFRESH_RATE = 5  # in seconds
    AMOUNT_TO_WRITE = 10 * 1024 ** 3
    HA_TIMEOUT = 300
    SLEEP_TIME = 60  # Time to idle before going to block the edge
    FIO_BIN_EE = {'url': 'http://www.include.gr/fio.bin.latest.ee', 'location': '/tmp/fio.bin.latest'}
    FIO_BIN = {'url': 'http://www.include.gr/fio.bin.latest', 'location': '/tmp/fio.bin.latest'}

    @staticmethod
    # @gather_results(CASE_TYPE, LOGGER, TEST_NAME)
    def main(blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        return EdgeTester._execute_test()

    @staticmethod
    def _execute_test():
        with open(CONFIG_LOC, 'r') as config_file:
            config = json.load(config_file)
        local_api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )
        # This test needs the api of another node which does not have the magic packet
        # Currently adding it statically, do not see another option
        # remote_api = OVSClient('10.100.187.31', 'admin', 'admin')  # This is a non apt-ee envir and should not be able to connect here
        # try:
        #     compute_client = SSHClient('10.100.187.31', username='root', password='rooter')
        # except Exception as ex:
        #     raise RuntimeError('Could not setup the compute client. Got {}'.format(str(ex)))

        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 2 and vp.configuration['dtl_mode'] == 'sync':
                vpool = vp
                break
        assert vpool is not None, 'Not enough vPools to test. We need at least a vPool with 2 storagedrivers'
        available_storagedrivers = [storagedriver for storagedriver in vpool.storagedrivers]
        std_1 = available_storagedrivers.pop(random.randrange(len(available_storagedrivers)))
        std_2 = available_storagedrivers.pop(random.randrange(len(available_storagedrivers)))
        str_1 = std_1.storagerouter  # Will act as volumedriver node
        str_2 = std_2.storagerouter  # Will act as volumedriver node
        str_3 = [storagerouter for storagerouter in StoragerouterHelper.get_storagerouters() if storagerouter.guid not in [str_1.guid, str_2.guid]][0]  # Will act as compute node
        compute_client = SSHClient(str_3, username='root')  # Compute node is excluded from all migrations and shutdowns
        EdgeTester.LOGGER.info('Chosen destination storagedriver is: {0}'.format(std_1.storage_ip))
        EdgeTester.LOGGER.info('Chosen original owning storagedriver is: {0}'.format(std_2.storage_ip))

        cluster_info = {'storagerouters': {'str1': str_1, 'str2': str_2, 'str3': str_3}, 'storagedrivers': {'std1': std_1, 'std2': std_2}}
        installed_versions = PackageManager.get_installed_versions(client=compute_client)
        is_ee = 'volumedriver-ee-base' in installed_versions
        if is_ee is True:
            fio_bin_loc = EdgeTester.FIO_BIN_EE['location']
            fio_bin_url = EdgeTester.FIO_BIN_EE['url']
        else:
            fio_bin_loc = EdgeTester.FIO_BIN['location']
            fio_bin_url = EdgeTester.FIO_BIN['url']

        compute_client.run(['wget', fio_bin_url, '-O', fio_bin_loc])
        compute_client.file_chmod(fio_bin_loc, 755)
        try:
            EdgeTester.test_rerout_fio(fio_bin_loc, vpool, compute_client, cluster_info, local_api, is_ee=is_ee)
        except Exception:
            # compute_client.file_delete(fio_bin_loc)
            raise

    @staticmethod
    def adjust_for_rerout(storagerouter, start_port=None, end_port=None, trigger_rerout=True, ip_to_block=None, additional_ports=None):
        """
        Force edge to rerout. Done by blocking all connections to the volumedriver port
        :param storagerouter: storagerouter object of the node to execute the rerout on
        :type storagerouter: ovs.dal.hybrids.storagerouter.StorageRouter
        :param start_port: port to start blocking
        :type start_port: int/str
        :param end_port: port to end blocking
        :type end_port: int/str
        :param trigger_rerout: trigger or unblock the rerout
        :type trigger_rerout: bool
        :param ip_to_block: ip to block connections on
        :type ip_to_block: str
        :param additional_ports: additional ports to block outside of the range
        :type additional_ports: list[int] / list[str]
        :return: 
        """
        if (start_port is None or end_port is None) and ip_to_block is None and additional_ports is None:
            raise ValueError('Something to block is required. Be it a range, extra ports or an IP')
        ports = []
        if start_port is not None and end_port is not None:
            if 22 in xrange(int(end_port), int(start_port)):  # Avoid blocking ssh
                raise ValueError('Port 22 cannot be included in the ports.')
            ports.append("{0}:{1}".format(start_port, end_port))
        if isinstance(additional_ports, list):
            ports.extend([str(item) for item in additional_ports])  # Cast to str
        cmds = {}
        if trigger_rerout is True:
            cmds['input'] = ["iptables", "-I", "INPUT", "1"]  # Insert because first rule applies first.
            cmds['output'] = ["iptables", "-I", "OUTPUT", "1"]
        else:
            cmds['input'] = ["iptables", "-D", "INPUT"]
            cmds['output'] = ["iptables", "-D", "OUTPUT"]
            EdgeTester.LOGGER.debug('Opening {}'.format(','.join(ports)))
        if isinstance(ip_to_block, str) or isinstance(ip_to_block, unicode):
            ip_extra = ['--source', ip_to_block]
            cmds['input'].extend(ip_extra)
            cmds['output'].extend(ip_extra)
        protocol_rule = ["--protocol", "tcp"]
        cmds['input'].extend(protocol_rule)
        cmds['output'].extend(protocol_rule)
        if len(ports) > 0:
            port_rule = ["--match", "multiport", "--dport", ','.join(ports)]
            cmds['input'].extend(port_rule)
            cmds['output'].extend(port_rule)
        action = ["-j", "DROP"]
        cmds['input'].extend(action)
        cmds['output'].extend(action)
        client = SSHClient(storagerouter, username='root')
        for rule_key, cmd in cmds.iteritems():
            EdgeTester.LOGGER.debug('Executing {0} on {1}'.format(storagerouter.ip, ' '.join(cmd)))
            client.run(cmd)

    @staticmethod
    def test_rerout_fio(fio_bin_path, vpool, compute_client, cluster_info, api, disk_amount=1, timeout=HA_TIMEOUT, is_ee=False):
        """
        Uses a modified fio to work with the openvstorage protocol
        :param fio_bin_path: path of the fio binary
        :type fio_bin_path: str
        :param compute_client: client of the machine to execute the fio
        :type compute_client: ovs.extensions.generic.sshclient.SSHClient
        :param vpool: vpool DAL object of the vpool to use
        :type vpool: ovs.dal.hybrids.vpool.VPool
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :param api: api object to call the ovs api
        :type api: ci.api_lib.helpers.api.OVSClient
        :param disk_amount: amount of disks to test fail over with
        :type disk_amount: int
        :param timeout: timeout in seconds
        :type timeout: int
        :param is_ee: is it the enterprise edition
        :type is_ee: bool
        :return: None
        :rtype: NoneType
        """
        logger = EdgeTester.LOGGER
        str_2 = cluster_info['storagerouters']['str2']
        std_1 = cluster_info['storagedrivers']['std1']
        std_2 = cluster_info['storagedrivers']['std2']  # will be downed

        values_to_check = {
            'source_std': std_2.serialize(),
            'target_std': std_1.serialize(),
            'vdisks': []
        }
        # Create vdisks
        protocol = std_2.cluster_node_config['network_server_uri'].split(':')[0]
        edge_configuration = {'fio_bin_location': fio_bin_path, 'hostname': std_2.storage_ip,
                              'port': std_2.ports['edge'],
                              'protocol': protocol,
                              'volumename': []}
        vdisk_info = {}
        failed_configurations = []

        ee_info = None
        if is_ee is True:
            # @ Todo create user instead
            ee_info = {'username': 'root', 'password': 'rooter'}

        for index in xrange(0, disk_amount):
            try:
                vdisk_name = '{0}_vdisk{1}'.format(EdgeTester.TEST_NAME, str(index).zfill(3))
                data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(vdisk_name, vpool.name, EdgeTester.AMOUNT_TO_WRITE, std_2.storage_ip, api))
                vdisk_info[vdisk_name] = data_vdisk
                edge_configuration['volumename'].append(data_vdisk.devicename.rsplit('.', 1)[0].split('/', 1)[1])
                values_to_check['vdisks'].append(data_vdisk.serialize())
            except RuntimeError as ex:
                logger.error('Could not create the vdisk. Got {0}'.format(str(ex)))
                raise
        for configuration in EdgeTester.DATA_TEST_CASES:
            threads = []
            screen_names = []
            failed_over = False
            r_semaphore = None
            adjusted = False
            edge_ports_to_close = []
            try:
                logger.info('Starting threads.')  # Separate because creating vdisks takes a while, while creating the threads does not
                monitoring_data = {}
                current_thread_bundle = {'index': 1, 'vdisks': []}
                required_thread_amount = math.ceil(len(vdisk_info.keys()) / EdgeTester.VDISK_THREAD_LIMIT)
                r_semaphore = Waiter(required_thread_amount + 1, auto_reset=True)  # Add another target to let this thread control the semaphore
                for index, (vdisk_name, vdisk_object) in enumerate(vdisk_info.iteritems(), 1):
                    vdisks = current_thread_bundle['vdisks']
                    volume_number_range = '{0}-{1}'.format(current_thread_bundle['index'], index)
                    vdisks.append(vdisk_object)
                    if index % EdgeTester.VDISK_THREAD_LIMIT == 0 or index == len(vdisk_info.keys()):
                        # New thread bundle
                        monitor_resource = {'general': {'io': [], 'edge_clients': {}}}
                        # noinspection PyTypeChecker
                        for vdisk in vdisks:
                            monitor_resource[vdisk.name] = {'io': {'down': [], 'descending': [], 'rising': [], 'highest': None, 'lowest': None},
                                                            'edge_clients': {'down': [], 'up': []}}
                        monitoring_data[volume_number_range] = monitor_resource
                        threads.append(ThreadHelper.start_thread_with_event(EdgeTester._monitor_changes,
                                                                            name='iops_{0}'.format(current_thread_bundle['index']),
                                                                            args=(monitor_resource, vdisks, r_semaphore)))
                        current_thread_bundle['index'] = index + 1
                        current_thread_bundle['vdisks'] = []
                try:
                    screen_names = EdgeTester._write_data(compute_client, 'fio', configuration, edge_configuration, ee_info=ee_info)
                except Exception as ex:
                    logger.error('Could not start threading. Got {0}'.format(str(ex)))
                    raise
                logger.info('Doing IO for {0}s before down the connection the owner node.'.format(EdgeTester.SLEEP_TIME))
                now = time.time()
                while time.time() - now < EdgeTester.SLEEP_TIME:
                    if r_semaphore.get_counter() < required_thread_amount:
                        time.sleep(0.05)
                        continue
                    if time.time() - now % 1 == 0:
                        io_volumes = EdgeTester._get_all_vdisks_with_io(monitoring_data)
                        logger.info('Currently got io for {0} volumes: {1}'.format(len(io_volumes), io_volumes))
                    r_semaphore.wait()
                # Wait again to sync
                EdgeTester.LOGGER.info('Syncing threads')
                while r_semaphore.get_counter() < required_thread_amount:
                    time.sleep(0.05)
                # Threads ready for monitoring at this point
                #########################
                # Bringing original owner of the volume down
                #########################
                for edge_clients in EdgeTester._get_all_edge_clients(monitoring_data).values():
                    for edge_client in edge_clients:
                        edge_ports_to_close.append(str(edge_client['port']))
                try:
                    EdgeTester.adjust_for_rerout(std_2.storagerouter, trigger_rerout=True, ip_to_block=compute_client.ip)
                    adjusted = True
                    downed_time = time.time()
                except Exception as ex:
                    logger.error('Failed to stop. Got {0}'.format(str(ex)))
                    raise
                time.sleep(EdgeTester.IO_REFRESH_RATE)
                # Start IO polling
                r_semaphore.wait()
                try:
                    while True:
                        if time.time() - downed_time > timeout:
                            raise RuntimeError('HA test timed out after {0}s.'.format(timeout))
                        if r_semaphore.get_counter() < required_thread_amount:
                            time.sleep(1)
                            continue
                        # Calculate to see if IO is back
                        io_volumes = EdgeTester._get_all_vdisks_with_io(monitoring_data)
                        logger.info('Currently got io for {0}: {1}'.format(len(io_volumes), io_volumes))
                        if len(io_volumes) == disk_amount:
                            logger.info('All threads came through with IO at {0}. Waited {1}s for IO.'.format(datetime.today().strftime('%Y-%m-%d %H:%M:%S'), time.time() - downed_time))
                            failed_over = True
                            break
                        logger.info('IO has not come through for {0}s.'.format(time.time() - downed_time))
                        r_semaphore.wait()
                        time.sleep(1)
                except Exception:
                    raise
                finally:
                    # Wait again to sync so we can properly abort the threads
                    EdgeTester.LOGGER.info('Syncing threads')
                    while r_semaphore.get_counter() < required_thread_amount:
                        time.sleep(0.05)
                EdgeTester._validate_dal(values_to_check)
            except Exception as ex:
                # @ TODO remove raise
                raise
                logger.error('Got an exception while running configuration {}. Namely: {}'.format(configuration, str(ex)))
                failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
            finally:
                if adjusted is True:
                    EdgeTester.adjust_for_rerout(std_2.storagerouter, trigger_rerout=False, ip_to_block=compute_client.ip)
                if screen_names:
                    for screen_name in screen_names:
                        pass  #@ Todo uncomment and remove pass
                        # compute_client.run(['screen', '-S', screen_name, '-X', 'quit'])
                try:
                    logger.info('Stopping iops monitoring')
                    for thread_pair in threads:
                        if thread_pair[0].isAlive():
                            thread_pair[1].set()
                    if r_semaphore:
                        r_semaphore.wait()
                    # Wait for threads to die
                    for thread_pair in threads:
                        thread_pair[0].join()
                except Exception as ex:
                    logger.warning('Stopping the threads failed. Got {0}'.format(str(ex)))
                if failed_over:
                    # Wait for the downed node to come back up
                    to_be_downed_client = None
                    while to_be_downed_client is None:
                        try:
                            to_be_downed_client = SSHClient(str_2, username='root')
                        except:
                            pass
                        time.sleep(1)
                    services = ServiceManager.list_services(to_be_downed_client)
                    for service in services:
                        if vpool.name not in service:
                            continue
                        while ServiceManager.get_service_status(service, to_be_downed_client)[0] is False:
                            time.sleep(1)
                    for vdisk_name, vdisk_object in vdisk_info.iteritems():
                        VDiskSetup.move_vdisk(vdisk_guid=vdisk_object.guid, target_storagerouter_guid=str_2.guid, api=api)

        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(failed_configurations)

    @staticmethod
    def _write_data(client, cmd_type, configuration, edge_configuration=None, screen=True, data_to_write=AMOUNT_TO_WRITE,
                    file_locations=None, ee_info=None):
        """
        Fire and forget an IO test
        Starts a screen session detaches the sshclient
        :param client: ovs ssh client for the vm
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param cmd_type: type of command. Was used to differentiate between dd and fio
        :type cmd_type: str
        :param configuration: configuration params for fio. eg (10, 90) first value represents read, second one write percentage
        :type configuration: tuple
        :param edge_configuration: configuration to fio over edge
        :type edge_configuration: dict
        :return: list of screen names (empty if screen is False)
        :rtype: list
        """
        bs = '4k'
        iodepth = 32
        write_size = data_to_write
        cmds = []
        screen_names = []
        if cmd_type != 'fio':
            raise ValueError('{0} is not supported for writing data.'.format(cmd_type))
        config = ['--iodepth={0}'.format(iodepth), '--rw=randrw', '--bs={0}'.format(bs), '--direct=1',
                  '--rwmixread={0}'.format(configuration[0]), '--rwmixwrite={0}'.format(configuration[1]), '--randrepeat=0']
        if edge_configuration:
            fio_vdisk_limit = EdgeTester.FIO_VDISK_LIMIT
            volumes = edge_configuration['volumename']
            fio_amount = int(math.ceil(float(len(volumes)) / fio_vdisk_limit))
            for fio_nr in xrange(0, fio_amount):
                vols = volumes[fio_nr * fio_vdisk_limit: (fio_nr + 1) * fio_vdisk_limit]
                additional_settings = ['ulimit -n 4096;']  # Volumedriver envir params
                # Append edge fio stuff
                additional_config = ['--ioengine=openvstorage', '--hostname={0}'.format(edge_configuration['hostname']),
                                     '--port={0}'.format(edge_configuration['port']), '--protocol={0}'.format(edge_configuration['protocol']),
                                     '--enable_ha=1', '--group_reporting=1']
                if ee_info is not None:
                    additional_config.extend(['--username={0}'.format(ee_info['username']), '--password={0}'.format(ee_info['password'])])
                verify_config = ['--verify=crc32c-intel', '--verifysort=1', '--verify_fatal=1', '--verify_backlog=1000000']
                # Generate test names for each volume
                volumes = edge_configuration['volumename']
                if isinstance(volumes, str):
                    volumes = [volumes]
                if not isinstance(volumes, list):
                    raise TypeError('Volumes should be string or list')
                fio_jobs = []
                for index, volume in enumerate(vols):
                    fio_jobs.append('--name=test{0}'.format(index))
                    fio_jobs.append('--volumename={0}'.format(volume))
                cmds.append(additional_settings + [edge_configuration['fio_bin_location']] + config + additional_config + verify_config + fio_jobs)
        else:
            fio_jobs = []
            if file_locations:
                for index, file_location in enumerate(file_locations):
                    fio_jobs.append('--name=test{0}'.format(index))
                    fio_jobs.append('--filename={0}'.format(file_location))
            additional_config = ['--ioengine=libaio', '--size={0}'.format(write_size)]
            cmds.append(['fio'] + config + additional_config + fio_jobs)
        if screen is True:
            # exec bash to keep it running
            for index, cmd in enumerate(cmds):
                screen_name = 'fio_{0}'.format(index)
                # cmds[index] = 'screen -S {0} -dm bash -c "while {1}; do :; done; exec bash"'.format(screen_name, ' '.join(cmd))
                cmds[index] = ['screen', '-S', screen_name, '-dm', 'bash', '-c', 'while {0}; do :; done; exec bash'.format(' '.join(cmd))]
                screen_names.append(screen_name)
        for cmd in cmds:
            EdgeTester.LOGGER.info('Writing data with: {0}'.format(' '.join(cmd)))
            client.run(cmd)
        return screen_names

    @staticmethod
    def _get_all_edge_clients(monitoring_data):
        output = {}
        for volume_number_range, monitor_resource in monitoring_data.iteritems():
            output.update(monitor_resource['general']['edge_clients'])
        return output

    @staticmethod
    def _get_all_vdisks_with_io(monitoring_data):
        output = []
        for volume_number_range, monitor_resource in monitoring_data.iteritems():
            output.extend(monitor_resource['general']['io'])
        return output

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
        target_std = StoragedriverHelper.get_storagedriver_by_guid(values['target_std']['guid'])  # Should not have moved to here
        for serialized_vdisk in values['vdisks']:
            vdisk = VDiskHelper.get_vdisk_by_guid(serialized_vdisk['guid'])
            # Expecting no changes in vdisks_guids
            if vdisk.guid in source_std.vdisks_guids:
                EdgeTester.LOGGER.info('Vdisks were not moved according the DAL.')
            else:
                raise ValueError('Vdisks were moved according the DAL.')
            if vdisk.guid not in target_std.vdisks_guids:
                EdgeTester.LOGGER.info('Vdisks were not moved to the target according the DAL.')
            else:
                raise ValueError('Vdisks guids were updated after move for target storagedriver.')
            if vdisk.storagerouter_guid == source_std.storagerouter.guid:
                EdgeTester.LOGGER.info('Owner has remained the same.')
            else:
                ValueError('Expected {0} but found {1} for vdisk.storagerouter_guid'.format(source_std.storagerouter.guid, vdisk.storagerouter_guid))
        EdgeTester.LOGGER.info('Move vdisk was successful according to the dal (which fetches volumedriver info).')
    
    @staticmethod
    def _monitor_changes(results, vdisks, r_semaphore, stop_event):
        """
        Threading method that will check for IOPS downtimes
        :param results: variable reserved for this thread
        :type results: dict
        :param vdisks: vdisk object
        :type vdisks: list(ovs.dal.hybrids.vdisk.VDISK)
        :param r_semaphore: semaphore object to lock threads
        :type r_semaphore: ovs.extensions.generic.threadhelpers.Waiter
        :param stop_event: Threading event to watch for
        :type stop_event: threading._Event
        :return: None
        :rtype: NoneType
        """
        last_recorded_iops = {}
        while not stop_event.is_set():
            general_info = results['general']
            general_info['in_progress'] = True
            has_io = []
            edge_info = {}
            for vdisk in vdisks:
                edge_info[vdisk.name] = []
            # Reset counters
            general_info['io'] = has_io
            general_info['edge_clients'].update(edge_info)
            now = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
            now_sec = time.time()
            for vdisk in vdisks:
                last_iops = last_recorded_iops.get(vdisk.name, 0)
                result = results[vdisk.name]
                vdisk_stats = vdisk.statistics
                vdisk_edge_clients = vdisk.edge_clients
                current_iops = vdisk_stats['4k_read_operations_ps'] + vdisk_stats['4k_write_operations_ps']
                io_section = result['io']
                if current_iops == 0:
                    io_section['down'].append((now, current_iops))
                else:
                    has_io.append(vdisk.name)
                    if last_iops >= current_iops:
                        io_section['rising'].append((now, current_iops))
                    else:
                        io_section['descending'].append((now, current_iops))
                    if current_iops > io_section['highest'] or io_section['highest'] is None:
                        io_section['highest'] = current_iops
                    if current_iops < io_section['lowest'] or io_section['lowest'] is None:
                        io_section['lowest'] = current_iops
                edge_client_section = result['edge_clients']
                edge_info[vdisk.name] = vdisk_edge_clients
                if len(vdisk_edge_clients) == 0:
                    edge_client_section['down'].append((now, vdisk_edge_clients))
                else:
                    edge_client_section['up'].append((now, vdisk_edge_clients))
                # Sleep to avoid caching
                last_recorded_iops[vdisk.name] = current_iops
            general_info['io'] = has_io
            general_info['edge_clients'].update(edge_info)
            duration = time.time() - now_sec
            EdgeTester.LOGGER.debug('IO for {0} at {1}. Call took {2}'.format(has_io, now, duration))
            EdgeTester.LOGGER.debug('Edge clients for {0} at {1}. Call took {2}'.format(edge_info, now, duration))
            general_info['in_progress'] = False
            time.sleep(0 if duration > EdgeTester.IO_REFRESH_RATE else EdgeTester.IO_REFRESH_RATE - duration)
            r_semaphore.wait(30 * 60)  # Let each thread wait for another
            
                
def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return EdgeTester().main(blocked)

if __name__ == '__main__':
    run()
