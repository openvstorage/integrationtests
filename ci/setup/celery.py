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
from ovs.extensions.generic.configuration import Configuration


class CelerySetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_celery_setup")
    SCHEDULED_TASK_CFG = "/ovs/framework/scheduling/celery"

    def __init__(self):
        pass

    @staticmethod
    def override_schedule_tasks(configuration):
        """
        Override the scheduled tasks crontab with your own confguration

        :param configuration: configuration to override scheduled tasks
        :type configuration: dict
        :return:
        """

        Configuration.set(CelerySetup.SCHEDULED_TASK_CFG, configuration)
        return cmp(Configuration.get(CelerySetup.SCHEDULED_TASK_CFG, configuration), configuration) == 0
