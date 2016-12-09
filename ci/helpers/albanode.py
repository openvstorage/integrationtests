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
import requests
from requests.auth import HTTPBasicAuth
from ovs.log.log_handler import LogHandler
from ovs.dal.hybrids.albanode import AlbaNode
from ovs.dal.lists.albanodelist import AlbaNodeList
from ci.helpers.asdmanager import ASDManagerClient


class AlbaNodeHelper(object):
    """
    Alba node helper class
    """

    LOGGER = LogHandler.get(source='helpers', name="ci_albanode")
    IGNORE_KEYS = ('_error', '_duration', '_version', '_success')

    @staticmethod
    def _map_alba_nodes(api):
        """
        Will map the alba_node_id with its guid counterpart and return the map dict
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        """
        mapping = {}

        options = {
            'contents': 'node_id,_relations',
        }
        response = api.get(
            api='alba/nodes',
            params=options
        )
        for node in response['data']:
            mapping[node['node_id']] = node['guid']

        return mapping

    @staticmethod
    def get_albanode(guid):
        """
        Fetches an albanode object by guid

        :param guid: guid of albanode
        :type guid: str
        :return: ovs.dal.hybrids.albanode.AlbaNode
        """
        return AlbaNode(guid)

    @staticmethod
    def get_albanode_by_ip(ip):
        """
        Fetches an albanode object by ip

        :param ip: ip of the node
        :type ip: str
        :return: ovs.dal.hybrids.albanode.AlbaNode
        """
        return AlbaNodeList.get_albanode_by_ip(ip)

    @staticmethod
    def get_disk_by_ip(ip, diskname):
        albanode = AlbaNodeHelper.get_albanode_by_ip(ip)
        mapping = AlbaNodeHelper._map_node_disks(albanode)
        if diskname in mapping:
            return {"diskname": diskname,
                    "aliases": mapping[diskname]
                    }
        else:
            raise KeyError('Did not find disk {0} in the mapping for albanode with ip {1}. Currently mapped {2}'.format(diskname, ip, mapping))

    @staticmethod
    def _map_node_disks(albanode):
        asd_client = ASDManagerClient(albanode)
        mapping = {}
        disks = asd_client.get_disks()
        for alias, disk in disks.iteritems():
            # Get diskname
            diskname = disk['device'].split('/')[-1]
            # Map aliases to the diskname
            mapping[diskname] = disk['aliases']
        return mapping
