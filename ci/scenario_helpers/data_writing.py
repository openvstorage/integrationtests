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
import math
import uuid
from ovs.log.log_handler import LogHandler
from ovs.lib.helpers.toolbox import Toolbox


class DataWriter(object):
    """
    Class that handles writing data
    Used in many tests which require IO.
    """
    LOGGER = LogHandler.get(source='scenario_helpers', name='data_writer')
    FIO_VDISK_LIMIT = 50

    @classmethod
    def write_data_fio(cls, client, fio_configuration, edge_configuration=None, file_locations=None, fio_vdisk_limit=FIO_VDISK_LIMIT,
                       screen=True, loop_screen=True, logger=LOGGER):
        """
        Start writing data using fio
        Will output to files within /tmp/
        :param client: 
        :param fio_configuration: configuration for fio. Specify iodepth and bs
        :type fio_configuration: dict {'bs': '4k', 'iodepth': 32}
        :param edge_configuration: configuration to fio over edge -OPTIONAL eg {'port': 26203, 'hostname': 10.100.10.100, 'protocol': tcp|udp, 'fio_bin_location': /tmp/fio.bin, 'volumename': ['myvdisk00']}
        :type edge_configuration: dict
        :param file_locations: in conjunction with edge_configuration=None, points towards the files to perform fio on -OPTIONAL
        :type file_locations: list
        :param fio_vdisk_limit: amount of vdisks to handle with one fio instance. Defaults to 50
        :type fio_vdisk_limit: int
        :param screen: Offload to screen. Defaults to True
        :type screen: bool
        :param loop_screen: Keep looping the command in the screen. Defaults to True
        :type loop_screen: bool
        :param logger: logging instance
        :return: 
        """
        if edge_configuration is None and file_locations is None:
            raise ValueError('Either edge configuration or file_locations need to be specified')
        required_fio_params = {'bs': (str, None, False),  # Block size
                               'iodepth': (int, {'min': 1, 'max': 1024}, False),  # Iodepth, correlated to the amount of iterations to do
                               'output_format': (str, ['normal', 'terse', 'json'], False),  # Output format of fio
                               'io_size': (int, None),  # Nr of bytes to write/read
                               'configuration': (tuple, None)}  # configuration params for fio.First value represents read, second one write percentage eg (10, 90)
        Toolbox.verify_required_params(required_fio_params, fio_configuration)
        if isinstance(edge_configuration, dict):
            required_edge_params = {'volumenames': (list, str),
                                    'port': (int, {'min': 1, 'max': 65565}),
                                    'protocol': (str, ['tcp', 'udp', 'rdma']),
                                    'hostname': (str, None),
                                    'fio_bin_location': (str, None),
                                    'username': (str, None, False),
                                    'password': (str, None, False)}
            Toolbox.verify_required_params(required_edge_params, edge_configuration)
        bs = fio_configuration.get('bs', '4k')
        iodepth = fio_configuration.get('iodepth', 32)
        fio_output_format = fio_configuration.get('output_format', 'json')
        write_size = fio_configuration['io_size']
        configuration = fio_configuration['configuration']
        screen_names = []
        output_files = []
        cmds = []
        output_directory = '/tmp/data_write_{0}'.format(uuid.uuid4())
        client.dir_create(output_directory)
        cmd = ['--iodepth={0}'.format(iodepth), '--rw=randrw', '--bs={0}'.format(bs), '--direct=1',
               '--rwmixread={0}'.format(configuration[0]), '--rwmixwrite={0}'.format(configuration[1]),
               '--randrepeat=0']  # Base config for both edge fio and file fio
        if edge_configuration:
            volumes = edge_configuration['volumenames']
            fio_amount = int(math.ceil(float(len(volumes)) / fio_vdisk_limit))  # Amount of fio commands to prep
            for fio_nr in xrange(0, fio_amount):
                vols = volumes[fio_nr * fio_vdisk_limit: (fio_nr + 1) * fio_vdisk_limit]  # Subset the volume list
                current_cmd = ['ulimit -n 4096;', edge_configuration['fio_bin_location']] + cmd  # Volumedriver envir params + binary location prepended
                # Append edge fio stuff
                current_cmd.extend(['--ioengine=openvstorage', '--hostname={0}'.format(edge_configuration['hostname']),
                                    '--port={0}'.format(edge_configuration['port']),
                                    '--protocol={0}'.format(edge_configuration['protocol']),
                                    '--enable_ha=1', '--group_reporting=1'])  # HA config
                if edge_configuration.get('username') and edge_configuration.get('password'):
                    current_cmd.extend(['--username={0}'.format(edge_configuration['username']), '--password={0}'.format(edge_configuration['password'])])  # Credential config
                    current_cmd.extend(['--verify=crc32c-intel', '--verifysort=1', '--verify_fatal=1', '--verify_backlog=1000000'])  # Verify config
                output_file = '{0}/fio_{1}-{2}'.format(output_directory, fio_nr, len(vols))
                output_files.append(output_file)
                current_cmd.extend(['--output={0}'.format(output_file), '--output-format={0}'.format(fio_output_format)])  # Output config
                # Generate test names for each volume
                for index, volume in enumerate(vols):
                    current_cmd.append('--name=test{0}'.format(index))
                    current_cmd.append('--volumename={0}'.format(volume))  # Append fio jobs
                cmds.append(current_cmd)
        else:
            current_cmd = ['fio'] + cmd
            if file_locations:
                for index, file_location in enumerate(file_locations):
                    current_cmd.append('--name=test{0}'.format(index))
                    current_cmd.append('--filename={0}'.format(file_location))
            current_cmd.extend(['--ioengine=libaio', '--size={0}'.format(write_size)])
            output_file = '{0}/fio'.format(output_directory)
            output_files.append(output_file)
            current_cmd.extend(['--output={0}'.format(output_file), '--output-format={0}'.format(fio_output_format)])
            cmds.append(current_cmd)
        if screen is True:
            for index, cmd in enumerate(cmds):
                screen_name = 'fio_{0}'.format(str(index).zfill(3))
                cmds[index] = cls._prepend_screen(' '.join(cmd), screen_name, loop_screen)
                screen_names.append(screen_name)
        for cmd in cmds:
            logger.debug('Writing data with: {0}'.format(' '.join(cmd)))
            client.run(cmd)
        return screen_names, output_files

    @classmethod
    def write_data_vdbench(cls, client, binary_location, config_location, screen=True, loop_screen=True, logger=LOGGER):
        """
        @todo support output files
        Write data using vdbench.
        :param binary_location: 
        :param config_location: 
        :param screen: offload command to a screen 
        :param loop_screen: loop the screen command indefinitely
        :param logger: logging instance
        :return: list of screen names (empty if screen is False), list of output files (empty for vdbench)
        :rtype: tuple(list, list)
        """
        screen_names = []
        output_files = []
        cmd = [binary_location, '-vr', '-f', config_location]
        if screen is True:
            screen_name = 'vdbench_0'
            cmd = cls._prepend_screen(' '.join(cmd), screen_name, loop_screen)
            screen_names.append(screen_names)
        logger.debug('Writing data with: {0}'.format(' '.join(cmd)))
        client.run(cmd)
        return screen_names, output_files

    @staticmethod
    def deploy_vdbench(client, zip_remote_location, unzip_location, amount_of_errors, vdbench_config_path, lun_location,
                       thread_amount, write_amount, xfersize, read_percentage, random_seek_percentage,
                       io_rate, duration, interval, logger=LOGGER):
        """
        Deploy a vdbench config file
        :param client: client location
        :param zip_remote_location: zip location to fetch vdbench from
        :param unzip_location: destination for download and unzip location
        :param amount_of_errors: how many errors before vdbench stops
        :param vdbench_config_path: configuration file path for vdbench
        :param lun_location: what file to use to write/read to
        :param thread_amount: amount of worker threads
        :param write_amount: amount of data to process in bytes
        :param xfersize: data transfer size 
        :param read_percentage: percentage to read
        :param random_seek_percentage: how often a seek to a random lba will be generated
        :param io_rate: rate of the io
        :param duration: duration of the io
        :param interval: time between polling
        :param logger: logging instance
        :return: None
        """
        client.run(['apt-get', 'install', 'unzip', 'openjdk-9-jre-headless', '-y'])
        client.run(['wget', zip_remote_location, '-O', unzip_location])
        logger.info('Successfully fetched vdbench ZIP')
        client.run(['unzip', unzip_location])
        logger.info('Successfully unzipped vdbench ZIP')
        config_lines = [
            'data_errors={0}'.format(amount_of_errors),
            'sd=sd1,lun={0},threads={1},size={2}'.format(lun_location, thread_amount, write_amount),  # Storage definition
            'wd=wd1,sd=(sd1),xfersize={0},rdpct={1},seekpct={2},openflags=directio'.format(xfersize, read_percentage, random_seek_percentage),  # Set the workload
            'rd=rd1,wd=wd1,iorate={0},elapsed={1},interval={2}'.format(io_rate, duration, interval)  # Setup a run definition
        ]
        client.file_write(vdbench_config_path, '\n'.join(config_lines))
        logger.info('Successfully deployed config')

    @staticmethod
    def _prepend_screen(cmd, screenname, loop_screen=True):
        """
        Prepends necessary screen command to offload the command to a screen instance
        :param cmd: cmd to offload
        :param screenname: name of the screen
        :return: extended command
        """
        screen_cmd = ['screen', '-S', screenname, '-dm', 'bash', '-c']
        if loop_screen is True:
            screen_cmd.extend(['while {0}; do :; done; exec bash'.format(cmd)])
        else:
            screen_cmd.extend(['{0}; exec bash'.format(cmd)])
        return screen_cmd
