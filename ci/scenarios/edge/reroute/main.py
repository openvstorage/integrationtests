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
import time
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.domain import DomainHelper
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.helpers.storagedriver import StoragedriverHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.thread import ThreadHelper
from ci.autotests import gather_results
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.threading_handlers import ThreadingHandler
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class EdgeTester(CIConstants):
    """
    Test the edge magic
    """
    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = 'ci_scenario_edge_test'
    LOGGER = LogHandler.get(source='scenario', name=TEST_NAME)
    SLEEP_TIME = 60  # Time to idle before going to block the edge
    IO_TIME = 30

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME)
    def main(blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        return EdgeTester.start_test()

    @classmethod
    def start_test(cls):
        cluster_info, is_ee, fio_bin_loc = cls.setup()
        cls.test_reroute_fio(fio_bin_loc, cluster_info, is_ee=is_ee)

    @classmethod
    def setup(cls, logger=LOGGER):
        destination_str, source_str, compute_str = cls.get_storagerouters_for_ha()
        destination_storagedriver = None
        source_storagedriver = None
        storagedrivers_domain_sorted = DomainHelper.get_storagedrivers_in_same_domain(
            domain_guid=source_str.regular_domains[0])
        for storagedriver in storagedrivers_domain_sorted:
            if len(storagedriver.vpool.storagedrivers) < 2:
                continue
            if storagedriver.guid in destination_str.storagedrivers_guids:
                if destination_storagedriver is None and (
                        source_storagedriver is None or source_storagedriver.vpool_guid == storagedriver.vpool_guid):
                    destination_storagedriver = storagedriver
                    logger.info('Chosen destination storagedriver is: {0}'.format(destination_storagedriver.storage_ip))
                continue
            if storagedriver.guid in source_str.storagedrivers_guids:
                # Select if the source driver isn't select and destination is also unknown or the storagedriver has matches with the same vpool
                if source_storagedriver is None and (
                        destination_storagedriver is None or destination_storagedriver.vpool_guid == storagedriver.vpool_guid):
                    source_storagedriver = storagedriver
                    logger.info('Chosen source storagedriver is: {0}'.format(source_storagedriver.storage_ip))
                continue
        assert source_storagedriver is not None and destination_storagedriver is not None, 'We require at least two storagedrivers within the same domain.'

        cluster_info = {'storagerouters': {'destination': destination_str, 'source': source_str, 'compute': compute_str},
                        'storagedrivers': {'destination': destination_storagedriver, 'source': source_storagedriver}}
        source_client = SSHClient(source_str, username='root')
        compute_client = SSHClient(compute_str, username='root')

        is_ee = SystemHelper.get_ovs_version(source_client) == 'ee'
        if is_ee is True:
            fio_bin_loc = EdgeTester.FIO_BIN_EE['location']
            fio_bin_url = EdgeTester.FIO_BIN_EE['url']
        else:
            fio_bin_loc = EdgeTester.FIO_BIN['location']
            fio_bin_url = EdgeTester.FIO_BIN['url']

        compute_client.run(['wget', fio_bin_url, '-O', fio_bin_loc])
        compute_client.file_chmod(fio_bin_loc, 755)
        return cluster_info, is_ee, fio_bin_loc

    @staticmethod
    def adjust_for_reroute(storagerouter, start_port=None, end_port=None, trigger_rerout=True, ip_to_block=None, additional_ports=None):
        """
        Force edge to reroute. Done by blocking all connections to the volumedriver port
        :param storagerouter: storagerouter object of the node to execute the reroute on
        :type storagerouter: ovs.dal.hybrids.storagerouter.StorageRouter
        :param start_port: port to start blocking
        :type start_port: int/str
        :param end_port: port to end blocking
        :type end_port: int/str
        :param trigger_rerout: trigger or unblock the reroute
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
            cmds['input'].extend(["--match", "multiport", "--dport", ','.join(ports)])
            cmds['output'].extend(["--match", "multiport", "--sport", ','.join(ports)])
        action = ["-j", "DROP"]
        cmds['input'].extend(action)
        cmds['output'].extend(action)
        client = SSHClient(storagerouter, username='root')
        for rule_key, cmd in cmds.iteritems():
            EdgeTester.LOGGER.debug('Executing {0} on {1}'.format(storagerouter.ip, ' '.join(cmd)))
            client.run(cmd)

    @classmethod
    def test_reroute_fio(cls, fio_bin_path, cluster_info, disk_amount=1, timeout=CIConstants.HA_TIMEOUT, is_ee=False, logger=LOGGER):
        """
        Uses a modified fio to work with the openvstorage protocol
        :param fio_bin_path: path of the fio binary
        :type fio_bin_path: str
        :param cluster_info: information about the cluster, contains all dal objects
        :type cluster_info: dict
        :param disk_amount: amount of disks to test fail over with
        :type disk_amount: int
        :param timeout: timeout in seconds
        :type timeout: int
        :param is_ee: is it the enterprise edition
        :type is_ee: bool
        :param logger: logger instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: None
        :rtype: NoneType
        """
        api = cls.get_api_instance()
        compute_client = SSHClient(cluster_info['storagerouters']['compute'], username='root')

        destination_std = cluster_info['storagedrivers']['destination']
        source_std = cluster_info['storagedrivers']['source']  # will be downed
        vpool = source_std.vpool

        values_to_check = {
            'source_std': source_std.serialize(),
            'target_std': destination_std.serialize(),
            'vdisks': []
        }
        # Create vdisks
        protocol = source_std.cluster_node_config['network_server_uri'].split(':')[0]
        edge_configuration = {'fio_bin_location': fio_bin_path, 'hostname': source_std.storage_ip,
                              'port': source_std.ports['edge'],
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
                vdisk_name = '{0}_vdisk{1}'.format(EdgeTester.TEST_NAME, str(index).zfill(4))
                data_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_vdisk(vdisk_name, vpool.name, EdgeTester.AMOUNT_TO_WRITE * 2, source_std.storage_ip, api))
                vdisk_info[vdisk_name] = data_vdisk
                edge_configuration['volumename'].append(data_vdisk.devicename.rsplit('.', 1)[0].split('/', 1)[1])
                values_to_check['vdisks'].append(data_vdisk.serialize())
            except RuntimeError as ex:
                logger.error('Could not create the vdisk. Got {0}'.format(str(ex)))
                raise
        for configuration in EdgeTester.DATA_TEST_CASES:
            threads = {'evented': {'io': {'pairs': [], 'r_semaphore': None},
                                   'snapshots': {'pairs': [], 'r_semaphore': None}}}
            screen_names = []
            adjusted = False
            try:
                io_thread_pairs, monitoring_data, io_r_semaphore = ThreadingHandler.start_io_polling_threads(volume_bundle=vdisk_info)
                threads['evented']['io']['pairs'] = io_thread_pairs
                threads['evented']['io']['r_semaphore'] = io_r_semaphore
                screen_names, output_files = DataWriter.write_data(client=compute_client,
                                                                   cmd_type='fio',
                                                                   configuration=configuration,
                                                                   edge_configuration=edge_configuration,
                                                                   ee_info=ee_info,
                                                                   data_to_write=cls.AMOUNT_TO_WRITE)
                logger.info('Doing IO for {0}s before bringing down the node.'.format(cls.IO_TIME))
                ThreadingHandler.keep_threads_running(r_semaphore=threads['evented']['io']['r_semaphore'],
                                                      threads=threads['evented']['io']['pairs'],
                                                      shared_resource=monitoring_data,
                                                      duration=cls.IO_TIME)
                # Threads ready for monitoring at this point, they are waiting to resume
                EdgeTester.adjust_for_reroute(source_std.storagerouter, trigger_rerout=True, ip_to_block=compute_client.ip, additional_ports=[edge_configuration['port']])
                adjusted = True
                downed_time = time.time()
                logger.info('Now waiting two refreshrate intervals to avoid caching. In total {}s'.format(EdgeTester.IO_REFRESH_RATE * 2))
                time.sleep(cls.IO_REFRESH_RATE * 2)
                ThreadingHandler.poll_io(r_semaphore=threads['evented']['io']['r_semaphore'],
                                         required_thread_amount=len(threads),
                                         shared_resource=monitoring_data,
                                         downed_time=downed_time,
                                         timeout=timeout,
                                         output_files=output_files,
                                         client=compute_client,
                                         disk_amount=disk_amount)
                EdgeTester._validate_dal(values_to_check)  # Validate
            except Exception as ex:
                logger.error('Got an exception while running configuration {0}. Namely: {1}'.format(configuration, str(ex)))
                failed_configurations.append({'configuration': configuration, 'reason': str(ex)})
            finally:
                if adjusted is True:
                    EdgeTester.adjust_for_reroute(source_std.storagerouter, trigger_rerout=False, ip_to_block=compute_client.ip, additional_ports=[edge_configuration['port']])
                for screen_name in screen_names:
                    compute_client.run(['screen', '-S', screen_name, '-X', 'quit'])
                    for thread_category, thread_collection in threads['evented'].iteritems():
                        ThreadHelper.stop_evented_threads(thread_collection['pairs'], thread_collection['r_semaphore'])

        assert len(failed_configurations) == 0, 'Certain configuration failed: {0}'.format(failed_configurations)

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
