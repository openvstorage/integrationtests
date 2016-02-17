# Copyright 2016 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ConfigParser import RawConfigParser
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from StringIO import StringIO


class GeneralArakoon(object):
    """
    A general class dedicated to Arakoon logic
    """
    @staticmethod
    def get_config(cluster_name):
        """
        Retrieve the configuration for given cluster
        :param cluster_name: Name of the cluster
        :return: RawConfigParser object
        """
        etcd_key = '/ovs/arakoon/{0}/config'.format(cluster_name)
        if not EtcdConfiguration.exists(etcd_key, raw=True):
            raise ValueError('Unknown arakoon cluster_name {0} provided'.format(cluster_name))

        voldrv_config = EtcdConfiguration.get(etcd_key, raw=True)
        parser = RawConfigParser()
        parser.readfp(StringIO(voldrv_config))
        return parser
