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
import re
import math
import time
import threading
from datetime import datetime
from ci.api_lib.helpers.thread import ThreadHelper, Waiter
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.log.log_handler import LogHandler


class ThreadingHandler(CIConstants):
    """
    Contains methods using threads that are used across multiple tests
    """
    IO_REFRESH_RATE = 5  # in seconds
    LOGGER = LogHandler.get(source='scenario_helpers', name='threading_handler')
    VDISK_THREAD_LIMIT = 5  # Each monitor thread queries x amount of vdisks

    @staticmethod
    def monitor_changes(results, vdisks, r_semaphore, event, refresh_rate=IO_REFRESH_RATE, logger=LOGGER):
        """
        Threading method that will check for IOPS downtimes
        :param results: variable reserved for this thread
        :type results: dict
        :param vdisks: vdisk object
        :type vdisks: list(ovs.dal.hybrids.vdisk.VDISK)
        :param r_semaphore: semaphore object to lock threads
        :type r_semaphore: ovs.extensions.generic.threadhelpers.Waiter
        :param refresh_rate: interval between checking the io
        :param logger: logging instance
        :param event: Threading event to watch for
        :type event: threading._Event
        :return: None
        :rtype: NoneType
        """
        last_recorded_iops = {}
        while not event.is_set():
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
            logger.debug('IO for {0} at {1}. Call took {2}'.format(has_io, now, duration))
            logger.debug('Edge clients for {0} at {1}. Call took {2}'.format(edge_info, now, duration))
            general_info['in_progress'] = False
            time.sleep(0 if duration > refresh_rate else refresh_rate - duration)
            r_semaphore.wait(30 * 60)  # Let each thread wait for another

    @classmethod
    def start_io_polling_threads(cls, volume_bundle, logger=LOGGER):
        """
        Will start the io polling threads
        :param volume_bundle: bundle of volumes {vdiskname: vdisk object}
        :type volume_bundle: dict
        :param logger: logger instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: threads, monitoring_data, r_semaphore
        :rtype: tuple(list, dict, ci.api_lib.helpers.thread.Waiter)
        """
        required_thread_amount = math.ceil(float(len(volume_bundle.keys())) / cls.VDISK_THREAD_LIMIT)  # Amount of threads we will need
        r_semaphore = Waiter(required_thread_amount + 1, auto_reset=True)  # Add another target to let this thread control the semaphore
        threads = []
        monitoring_data = {}
        current_thread_bundle = {'index': 1, 'vdisks': []}
        logger.info(
            'Starting threads.')  # Separate because creating vdisks takes a while, while creating the threads does not
        try:
            for index, (vdisk_name, vdisk_object) in enumerate(volume_bundle.iteritems(), 1):
                vdisks = current_thread_bundle['vdisks']
                volume_number_range = '{0}-{1}'.format(current_thread_bundle['index'], index)
                vdisks.append(vdisk_object)
                if index % cls.VDISK_THREAD_LIMIT == 0 or index == len(volume_bundle.keys()):
                    # New thread bundle
                    monitor_resource = {'general': {'io': [], 'edge_clients': {}}}
                    # noinspection PyTypeChecker
                    for vdisk in vdisks:
                        monitor_resource[vdisk.name] = {
                            'io': {'down': [], 'descending': [], 'rising': [], 'highest': None, 'lowest': None},
                            'edge_clients': {'down': [], 'up': []}}
                    monitoring_data[volume_number_range] = monitor_resource
                    threads.append(ThreadHelper.start_thread_with_event(target=cls.monitor_changes,
                                                                        name='iops_{0}'.format(current_thread_bundle['index']),
                                                                        args=(monitor_resource, vdisks, r_semaphore)))
                    current_thread_bundle['index'] = index + 1
                    current_thread_bundle['vdisks'] = []
        except Exception:
            for thread_pair in threads:  # Attempt to cleanup current inflight threads
                if thread_pair[0].isAlive():
                    thread_pair[1].set()
            while r_semaphore.get_counter() < len(threads):  # Wait for the number of threads we currently have.
                time.sleep(0.05)
            r_semaphore.wait()  # Unlock them to let them stop (the object is set -> wont loop)
            # Wait for threads to die
            for thread_pair in threads:
                thread_pair[0].join()
            raise
        return threads, monitoring_data, r_semaphore

    @classmethod
    def poll_io(cls, r_semaphore, required_thread_amount, shared_resource, downed_time, disk_amount, timeout, output_files=None, client=None, logger=LOGGER):
        """
        Will start IO polling
        Prerequisite: all threads must have synced up before calling this function
        :param r_semaphore: Reverse semaphore, controlling object to sync the threads with
        :type r_semaphore: ci.api_lib.helpers.thread.Waiter
        :param required_thread_amount: Amount of threads that should be accounted for
        :type required_thread_amount: double / int
        :param shared_resource: Resources shared between all threads
        :type shared_resource: dict
        :param downed_time: Time to start timeout from
        :type downed_time: imt
        :param timeout: Seconds that can elapse before timing out
        :type timeout: int
        :param output_files: OPTIONAL: files that can be checked for errors (fio write data will do this)
        :type output_files: list[str]
        :param client: client that points towards the output files
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param disk_amount: amount of disks that were checked with
        :type disk_amount: int
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: None
        """
        if output_files is None and client is None:
            raise ValueError('When output files is specified, a compute client is needed.')
        if output_files is None:
            output_files = []
        r_semaphore.wait()  # Start IO polling
        while True:
            if time.time() - downed_time > timeout:
                raise RuntimeError('Polling timed out after {0}s.'.format(timeout))
            if r_semaphore.get_counter() < required_thread_amount:
                time.sleep(1)
                continue
            # Check if any errors occurred - possible due to the nature of the write data with screens
            # If the fio has had an error, it will break and output to the output file
            errors = set()
            for output_file in output_files:
                errors.update(set(
                    client.run('grep -a error {0} || true'.format(re.escape(output_file)), allow_insecure=True).splitlines()))
            if len(errors) > 0:
                raise RuntimeError('Fio has reported errors: {} at {}. Fetched from {}: {}'
                                   .format(', '.join(errors), datetime.today().strftime('%Y-%m-%d %H:%M:%S'), client.ip, ', '.join(output_files)))
            # Calculate to see if IO is back
            io_volumes = cls.get_all_vdisks_with_io(shared_resource)
            logger.info('Currently got io for {0}: {1}'.format(len(io_volumes), io_volumes))
            if len(io_volumes) == disk_amount:
                logger.info('All threads came through with IO at {0}. Waited {1}s for IO.'.format(
                    datetime.today().strftime('%Y-%m-%d %H:%M:%S'), time.time() - downed_time))
                break
            logger.info('IO has not come through for {0}s.'.format(time.time() - downed_time))
            if r_semaphore.get_counter() < required_thread_amount:
                if time.time() - downed_time > timeout:
                    raise RuntimeError('Polling timed out after {0}s.'.format(timeout))
                time.sleep(1)
            r_semaphore.wait()  # Unblock waiting threads

    @classmethod
    def keep_threads_running(cls, r_semaphore, threads, shared_resource, duration, logger=LOGGER):
        """
        Keeps the threads running for the duration
        :param r_semaphore: Reverse semaphore, controlling object to sync the threads with
        :type r_semaphore: ci.api_lib.helpers.thread.Waiter
        :param threads: list of threads with their closing object
        :type threads: list
        :param shared_resource: Resources shared between all threads
        :type shared_resource: dict
        :param duration: time to keep running
        :type duration: int
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :return: None
        """
        now = time.time()
        while time.time() - now < duration:
            if r_semaphore.get_counter() < len(threads):
                time.sleep(0.05)
                continue
            if time.time() - now % 1 == 0:
                io_volumes = cls.get_all_vdisks_with_io(shared_resource)
                logger.info('Currently got io for {0} volumes: {1}'.format(len(io_volumes), io_volumes))
            r_semaphore.wait()

    @staticmethod
    def get_all_edge_clients(monitoring_data):
        output = {}
        for volume_number_range, monitor_resource in monitoring_data.iteritems():
            output.update(monitor_resource['general']['edge_clients'])
        return output

    @staticmethod
    def get_all_vdisks_with_io(monitoring_data):
        output = []
        for volume_number_range, monitor_resource in monitoring_data.iteritems():
            output.extend(monitor_resource['general']['io'])
        return output

    @classmethod
    def start_snapshotting_threads(cls, volume_bundle, args=(), kwargs=None, logger=LOGGER):
        """
        Start the snapshotting threads
        :param volume_bundle: bundle of volumes
        :type volume_bundle: dict
        :param api: api instance
        :param logger: logging instance
        :return:
        """
        if kwargs is None:
            kwargs = {}
        threads = []
        current_thread_bundle = {'index': 1, 'vdisks': []}
        logger.info('Starting threads.')
        try:
            for index, (vdisk_name, vdisk_object) in enumerate(volume_bundle.iteritems(), 1):
                vdisks = current_thread_bundle['vdisks']
                vdisks.append(vdisk_object)
                if index % cls.VDISK_THREAD_LIMIT == 0 or index == len(volume_bundle.keys()):
                    threads.append(ThreadHelper.start_thread_with_event(target=cls._start_snapshots,
                                                                        name='iops_{0}'.format(
                                                                            current_thread_bundle['index']),
                                                                        args=(vdisks,) + args,
                                                                        kwargs=kwargs))
                    current_thread_bundle['index'] = index + 1
                    current_thread_bundle['vdisks'] = []
        except Exception:
            for thread_pair in threads:  # Attempt to cleanup current inflight threads
                if thread_pair[0].isAlive():
                    thread_pair[1].set()
            # Wait for threads to die
            for thread_pair in threads:
                thread_pair[0].join()
            raise
        return threads

    @classmethod
    def _start_snapshots(cls, vdisks, event, interval=60):
        """
        Threading code that creates snapshots every x seconds
        :param event: Threading event that will stop the while loop
        :type event: threading._Event
        :param interval: time between taking the snapshots
        :type interval: int
        :param vdisks: vdisk object
        :type vdisks: list(ovs.dal.hybrids.vdisk.VDISK)
        :return: None
        :rtype: NoneType
        """
        while not event.is_set():
            start = time.time()
            for vdisk in vdisks:
                VDiskSetup.create_snapshot(
                    snapshot_name='{0}_{1}'.format(vdisk.name, datetime.today().strftime('%Y-%m-%d %H:%M:%S')),
                    vdisk_name=vdisk.devicename,
                    vpool_name=vdisk.vpool.name,
                    consistent=False,
                    sticky=False)
            duration = time.time() - start
            time.sleep(0 if duration > interval else interval - duration)
