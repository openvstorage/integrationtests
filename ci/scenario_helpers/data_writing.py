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
import os
import math
import uuid
import errno
from ovs.log.log_handler import LogHandler


class DataWriter(object):
    """
    Class that handles writing data
    Used in many tests which require IO.
    """
    LOGGER = LogHandler.get(source='scenario_helpers', name='data_writer')
    FIO_VDISK_LIMIT = 50

    @classmethod
    def write_data(cls, client, cmd_type, configuration, data_to_write, fio_vdisk_limit=FIO_VDISK_LIMIT, edge_configuration=None,
                   screen=True, file_locations=None, ee_info=None, logger=LOGGER):
        """
        Write data to a specific host.
        Can write data within a screen
        :param client: ovs ssh client for the vm
        :type client: ovs.extensions.generic.sshclient.SSHClient
        :param cmd_type: type of command. Was used to differentiate between dd and fio
        :type cmd_type: str
        :param configuration: configuration params for fio.First value represents read, second one write percentage eg (10, 90)
        :type configuration: tuple
        :param data_to_write: amount of data to write eg 10 * 1024 ** 3
        :type data_to_write: int
        :param fio_vdisk_limit: amount of vdisks to handle with one fio instance. Defaults to 50
        :type fio_vdisk_limit: int
        :param edge_configuration: configuration to fio over edge -OPTIONAL eg {'port': 26203, 'hostname': 10.100.10.100, 'protocol': tcp|udp, 'fio_bin_location': /tmp/fio.bin, 'volumename': ['myvdisk00']}
        :type edge_configuration: dict
        :param screen: offload to screen
        :type screen: bool
        :param file_locations: in conjunction with edge_configuration=None, points towards the files to perform fio on -OPTIONAL
        :type file_locations: list
        :param ee_info: settings for the entreprise edition - OPTIONAL eg {'username': 'test', 'password': 'test'}
        :type ee_info: dict
        :param logger: logging instance
        :type logger: ovs.log.log_handler.LogHandler
        :raises OSError: if it fails to create a output directory
        :raises ValueError: if an unknown cmd_type is supplied
        :return: list of screen names (empty if screen is False), list of output files
        :rtype: tuple(list, list)
        """
        bs = '4k'
        iodepth = 32
        fio_output_format = 'json'
        write_size = data_to_write
        cmds = []
        screen_names = []
        output_files = []
        output_directory = '/tmp/data_write_{0}'.format(uuid.uuid4())
        client.dir_create(output_directory)
        try:
            os.makedirs(output_directory)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
        if cmd_type != 'fio':
            raise ValueError('{0} is not supported for writing data.'.format(cmd_type))
        config = ['--iodepth={0}'.format(iodepth), '--rw=randrw', '--bs={0}'.format(bs), '--direct=1',
                  '--rwmixread={0}'.format(configuration[0]), '--rwmixwrite={0}'.format(configuration[1]),
                  '--randrepeat=0']
        if edge_configuration:
            volumes = edge_configuration['volumename']
            fio_amount = int(math.ceil(float(len(volumes)) / fio_vdisk_limit))  # Amount of fio commands to prep
            for fio_nr in xrange(0, fio_amount):
                vols = volumes[fio_nr * fio_vdisk_limit: (fio_nr + 1) * fio_vdisk_limit]  # Subset the volume list
                additional_settings = ['ulimit -n 4096;']  # Volumedriver envir params
                # Append edge fio stuff
                additional_config = ['--ioengine=openvstorage', '--hostname={0}'.format(edge_configuration['hostname']),
                                     '--port={0}'.format(edge_configuration['port']),
                                     '--protocol={0}'.format(edge_configuration['protocol']),
                                     '--enable_ha=1', '--group_reporting=1']
                if ee_info is not None:
                    additional_config.extend(
                        ['--username={0}'.format(ee_info['username']), '--password={0}'.format(ee_info['password'])])
                verify_config = ['--verify=crc32c-intel', '--verifysort=1', '--verify_fatal=1',
                                 '--verify_backlog=1000000']
                output_file = '{0}/fio_{1}-{2}'.format(output_directory, fio_nr, len(vols))
                output_files.append(output_file)
                output_config = ['--output={0}'.format(output_file), '--output-format={0}'.format(fio_output_format)]
                # Generate test names for each volume
                fio_jobs = []
                for index, volume in enumerate(vols):
                    fio_jobs.append('--name=test{0}'.format(index))
                    fio_jobs.append('--volumename={0}'.format(volume))
                cmds.append(additional_settings + [edge_configuration['fio_bin_location']] + config + additional_config + verify_config + output_config + fio_jobs)
        else:
            fio_jobs = []
            if file_locations:
                for index, file_location in enumerate(file_locations):
                    fio_jobs.append('--name=test{0}'.format(index))
                    fio_jobs.append('--filename={0}'.format(file_location))
            additional_config = ['--ioengine=libaio', '--size={0}'.format(write_size)]
            output_file = '{0}/fio'.format(output_directory)
            output_files.append(output_file)
            output_config = ['--output={0}'.format(output_file), '--output-format={0}'.format(fio_output_format)]
            cmds.append(['fio'] + config + additional_config + output_config + fio_jobs)
        if screen is True:
            # exec bash to keep it running
            for index, cmd in enumerate(cmds):
                screen_name = 'fio_{0}'.format(index)
                cmds[index] = ['screen', '-S', screen_name, '-dm', 'bash', '-c',
                               'while {0}; do :; done; exec bash'.format(' '.join(cmd))]
                screen_names.append(screen_name)
        for cmd in cmds:
            logger.debug('Writing data with: {0}'.format(' '.join(cmd)))
            client.run(cmd)
        return screen_names, output_files

