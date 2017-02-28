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
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.services.service import ServiceManager
from ovs.lib.helpers.toolbox import Toolbox
from ovs.log.log_handler import LogHandler
from ovs.dal.hybrids.service import Service
from ovs.extensions.generic.sshclient import SSHClient


class ProxySetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_proxy_setup")
    PARAMS = {'ips': (list, Toolbox.regex_ip, False),
              'transport': (str, ['tcp', 'rdma'], False),
              'log_level': (str, ['info', 'debug'], False),
              'port': (int, {'min': 1024, 'max': 65535}, False),
              'albamgr_cfg_file': (str, None, False),
              'manifest_cache_size': (int, None, False),
              'fragment_cache': (list, None, False),
              'albamgr_connection_pool_size': (int, None, False),
              'nsm_host_connection_pool_size': (int, None, False),
              'osd_connection_pool_size': (int, None, False),
              'osd_timeout': (int, {'min': 0.5, 'max': 120}),
              'max_client_connections': (int, {'min': 10, 'max': 1024}, False),
              'tls_client': (dict, None, False),
              'use_fadvise': (str, ['true', 'false'], False),
              'upload_slack': (float, None, False),
              'read_preference': (list, None, False)}

    @staticmethod
    def configure_proxy(backend_name, proxy_configuration):
        faulty_keys = [key for key in proxy_configuration.keys() if key not in ProxySetup.PARAMS]
        if len(faulty_keys) > 0:
            raise ValueError('{0} are unsupported keys for proxy configuration.'.format(', '.join(faulty_keys)))
        Toolbox.verify_required_params(ProxySetup.PARAMS, proxy_configuration)
        vpools = VPoolList.get_vpools()
        with open('/root/old_proxies', 'w') as backup_file:
            for vpool in vpools:
                if vpool.metadata['backend']['backend_info']['name'] != backend_name:
                    continue
                for storagedriver in vpool.storagedrivers:
                    if hasattr(storagedriver, 'alba_proxies'):
                        for proxy in storagedriver.alba_proxies:
                            config_loc = 'ovs/vpools/{0}/proxies/{1}/config/main'.format(vpool.guid, proxy.guid)
                            proxy_service = Service(proxy.service_guid)
                            proxy_config = Configuration.get(config_loc)
                            old_proxy_config = dict(proxy_config)
                            backup_file.write('{} -- {}\n'.format(config_loc, old_proxy_config))
                            proxy_config.update(proxy_configuration)
                            ProxySetup.LOGGER.info("Changed {0} to {1} for proxy {2}".format(old_proxy_config, proxy_config, config_loc))
                            ProxySetup.LOGGER.info("Changed items {0}".format([(key, value) for key, value in proxy_config.iteritems() if key not in old_proxy_config.keys()]))
                            Configuration.set(config_loc, json.dumps(proxy_config, indent=4), raw=True)
                            client = SSHClient(storagedriver.storage_ip, username='root')
                            ServiceManager.restart_service(proxy_service.name, client=client)
