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

from ovs.log.log_handler import LogHandler
from ci.helpers.init_manager import InitManager
from ci.helpers.storagerouter import StoragerouterHelper
from ovs.extensions.generic.configuration import Configuration


class CelerySetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_celery_setup")
    SCHEDULED_TASK_CFG = "/ovs/framework/scheduling/celery"

    def __init__(self):
        pass

    @staticmethod
    def override_scheduletasks(configuration):
        """
        Override the scheduled tasks crontab with your own confguration

        :param configuration: configuration to override scheduled tasks
        :type configuration: dict
        :return:
        """
        service_name = 'ovs-watcher-framework'
        Configuration.set(CelerySetup.SCHEDULED_TASK_CFG, configuration)
        fetched_cfg = Configuration.get(CelerySetup.SCHEDULED_TASK_CFG, configuration)
        if cmp(fetched_cfg, configuration) == 0:
            # restart ovs-watcher-framework on all nodes
            for sr_ip in StoragerouterHelper.get_storagerouter_ips():
                if not InitManager.service_restart(service_name=service_name, ip=sr_ip):
                    CelerySetup.LOGGER.warning("`{0}` failed to restart on node `{1}`".format(service_name, sr_ip))
                    return False
            CelerySetup.LOGGER.info("Successfully restarted all `{0}` services!".format(service_name))
            return True
        else:
            CelerySetup.LOGGER.warning("`{0}` config is `{1}` but should be `{2}`"
                                       .format(CelerySetup.SCHEDULED_TASK_CFG, fetched_cfg, configuration))
            return False
