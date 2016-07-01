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

"""
A general class dedicated to Hypervisor logic
"""

import os
import re
import time
import urllib
import logging
import urlparse
from ci.tests.general.general import General
from ci.tests.general.general_openstack import GeneralOpenStack
from ovs.lib.helpers.toolbox import Toolbox
from ovs.lib.vdisk import VDiskController
from xml.dom import minidom



class GeneralHypervisor(object):
    """
    A general class dedicated to Hypervisor logic
    """

    @staticmethod
    def download_to_vpool(url, path, overwrite_if_exists=False):
        """
        Special method to download to vpool because voldrv does not support extending file at write
        :param url: URL to download from
        :param path: Path to download to
        :param overwrite_if_exists: Overwrite if file already exists
        :return: None
        """
        print url
        print path
        if os.path.exists(path) and not overwrite_if_exists:
            return
        u = urllib.urlopen(url)
        file_size = u.info()['Content-Length']
        bsize = 4096 * 1024
        VDiskController.create_volume(path, 0)
        with open(path, "wb") as f:
            size_written = 0
            os.ftruncate(f.fileno(), int(file_size))
            while 1:
                s = u.read(bsize)
                size_written += len(s)
                f.write(s)
                if len(s) < bsize:
                    break
        u.close()

    @staticmethod
    def get_hypervisor_type():
        """
        Retrieve type of hypervisor
        :return hypervisor type ['KVM'|'VMWARE']
        """
        config = General.get_config()
        return config.get('hypervisor', 'type')

    @staticmethod
    def get_hypervisor_info():
        """
        Retrieve info about hypervisor (ip, username, password)
        """
        config = General.get_config()
        # @TODO: Split these settings up in separate section or at least in 3 separate values in main
        hi = config.get(section='main', option='hypervisorinfo')
        hpv_list = hi.split(',')
        if not len(hpv_list) == 3:
            raise RuntimeError('No hypervisor info present in config')
        return hpv_list

    @staticmethod
    def set_hypervisor_info(ip, username, password):
        """
        Set info about hypervisor( ip, username and password )

        :param ip:         IP address of hypervisor
        :type ip:          String

        :param username:   Username for hypervisor
        :type username:    String

        :param password:   Password of hypervisor
        :type password:    String

        :return:           None
        """
        if not re.match(Toolbox.regex_ip, ip):
            print 'Invalid IP address specified'
            return False

        if type(username) != str or type(password) != str:
            print 'Username and password need to be str format'
            return False

        value = ','.join([ip, username, password])
        config = General.get_config()
        config.set(section='main', option='hypervisorinfo', value=value)
        General.save_config(config)
        return True


class Hypervisor(object):
    """
    Wrapper class for VMWare and KVM hypervisor classes
    """
    # Disable excessive logging
    logging.getLogger('suds.client').setLevel(logging.WARNING)
    logging.getLogger('suds.transport').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.schema').setLevel(logging.WARNING)
    logging.getLogger('suds.wsdl').setLevel(logging.WARNING)
    logging.getLogger('suds.resolver').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.query').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.basic').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.sxbasic').setLevel(logging.WARNING)
    logging.getLogger('suds.binding.marshaller').setLevel(logging.WARNING)
    logging.getLogger('suds.mx.literal').setLevel(logging.WARNING)
    logging.getLogger('suds.mx.core').setLevel(logging.WARNING)
    logging.getLogger('suds.sudsobject').setLevel(logging.WARNING)
    logging.getLogger('suds.metrics').setLevel(logging.WARNING)
    logging.getLogger('suds.xsd.sxbase').setLevel(logging.WARNING)
    logging.getLogger('plumbum.shell').setLevel(logging.WARNING)
    logging.getLogger('plumbum.local').setLevel(logging.WARNING)
