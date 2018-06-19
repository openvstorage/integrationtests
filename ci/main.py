#!/usr/bin/python

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

# This contains the general workflow of ovs that the testing suite will be executing
# Will stress test certain parts to ensure consistency
# Can validate and remove the testing parts on the go
# Depends upon a json-stylized configuration file
import json

from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.backend import BackendRemover
from ci.api_lib.remove.roles import RoleRemover
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.remove.vpool import VPoolRemover
from ci.api_lib.setup.arakoon import ArakoonSetup
from ci.api_lib.setup.backend import BackendSetup
from ci.api_lib.setup.celery import CelerySetup
from ci.api_lib.setup.domain import DomainSetup
from ci.api_lib.setup.proxy import ProxySetup
from ci.api_lib.setup.roles import RoleSetup
from ci.api_lib.setup.vpool import VPoolSetup

CONFIG_LOC = "/opt/OpenvStorage/ci/config/setup.json"
TEST_SCENARIO_LOC = "/opt/OpenvStorage/ci/scenarios/"
SETTINGS_LOC = "/opt/OpenvStorage/ci/config/settings.json"
TESTTRAIL_LOC = "/opt/OpenvStorage/ci/config/testtrail.json"

from ci.api_lib.helpers.ci_constants import CIConstants


class Workflow(object):
    try:
        from ovs.log.log_handler import LogHandler
        LOGGER = LogHandler.get(source='workflow', name="ci_workflow")
    except ImportError:
        from ovs.extensions.generic.logger import Logger
        LOGGER = Logger('workflow-ci_workflow')

    def __init__(self):

        self.config = CIConstants.SETUP_CFG
        self.api = CIConstants.api
        self.sr_info = {}


    @staticmethod
    def _run_task(target, args=(), kwargs=None):
        if kwargs is None:
            kwargs = {}
        while True:
            try:
                target(*args, **kwargs)
                break  # Break when success
            except Exception as ex:
                Workflow.LOGGER.warning('{0} failed with {1}.'.format(target, str(ex)))
                raise


    def run(self):
        Workflow._run_task(self.setup)
        self.configuration()
        if self.config['ci'].get('scenarios', False):
            Workflow._run_task(self.scenario)
        if self.config['ci'].get('cleanup', False):
            self.cleanup()

    def setup(self):
        """
        Setup a Open vStorage cluster based on a config file

        :return: None
        """

        if not self.config['ci']:
            Workflow.LOGGER.info("Skipped setup")
            return
        # Start setup
        Workflow.LOGGER.info("Starting setup")

        # Setup domains
        Workflow.LOGGER.info("Setup domains")
        for domain in CIConstants.DOMAIN_INFO:
            DomainSetup.add_domain(domain_name=domain)

        # Setup storagerouter (recovery) domains

        for storagerouter_ip, storagerouter_details in CIConstants.STORAGEROUTER_INFO.iteritems():
            self.sr_info[storagerouter_ip] = storagerouter_details

        for key, value in self.sr_info.items():
            self.sr_info[StoragerouterHelper.get_storagerouter_by_ip(key)] = value
            del self.sr_info[key]

        Workflow.LOGGER.info("Setup storagerouter (recovery) domains")
        for storagerouter_ip, storagerouter_details in CIConstants.STORAGEROUTER_INFO.iteritems():
            DomainSetup.link_domains_to_storagerouter(storagerouter_details['domains'], storagerouter_ip)

        # Setup disk roles
        Workflow.LOGGER.info("Setup disk roles")
        for storagerouter_ip, storagerouter_details in CIConstants.STORAGEROUTER_INFO.iteritems():
            for diskname, disk_details in storagerouter_details['disks'].iteritems():
                RoleSetup.add_disk_role(storagerouter_ip=str(storagerouter_ip), diskname=str(diskname), roles=disk_details['roles'])


        # Setup LOCAL backends
        Workflow.LOGGER.info("Setup `LOCAL` backends")
        for backend in CIConstants.BACKEND_INFO:
            if backend['scaling'] != "LOCAL":
                continue
            # check if possibly we need to setup external arakoons
            if 'external_arakoon' in backend:
                Workflow.LOGGER.info("Add external arakoons")
                ArakoonSetup.setup_external_arakoons(backend)
                Workflow.LOGGER.info("Finished adding external arakoons")

            BackendSetup.add_backend(backend_name=backend['name'], scaling="LOCAL")

            # checkup amount nsm_hosts for a backend if external_arakoon is specified
            if 'min_nsm_arakoons' in backend:
                Workflow.LOGGER.info("Setting min. {0} NSM hosts for {1}"
                                     .format(backend['min_nsm_arakoons'], backend['name']))
                ArakoonSetup.checkup_nsm_hosts(albabackend_name=backend['name'],
                                               amount=backend['min_nsm_arakoons'])
                Workflow.LOGGER.info("Finished setting min. {0} NSM hosts for {1}"
                                     .format(backend['min_nsm_arakoons'], backend['name']))

            # Add domains
            Workflow.LOGGER.info("Add domains")
            DomainSetup.link_domains_to_backend(domain_details=backend['domains'], albabackend_name=backend['name'])

            # Add presets
            Workflow.LOGGER.info("Add presets")
            for preset in backend['presets']:
                BackendSetup.add_preset(albabackend_name=backend['name'], preset_details=preset)

            # Initialize and claim asds
            Workflow.LOGGER.info("Initialize and claim asds")
            for storagenode_ip, disks in backend['osds'].iteritems():
                BackendSetup.add_asds(albabackend_name=backend['name'], target=storagenode_ip, disks=disks)

        # Setup GLOBAL backends
        Workflow.LOGGER.info("Setup `GLOBAL` backends")
        for backend in CIConstants.BACKEND_INFO:
            if backend['scaling'] != "GLOBAL":
                continue
            # check if possibly we need to setup external arakoons
            if 'external_arakoon' in backend:
                Workflow.LOGGER.info("Add external arakoons")
                ArakoonSetup.setup_external_arakoons(backend)
                Workflow.LOGGER.info("Finished adding external arakoons")

            BackendSetup.add_backend(backend_name=backend['name'], scaling="GLOBAL")

            # checkup amount nsm_hosts for a backend if external_arakoon is specified
            if 'min_nsm_arakoons' in backend:
                Workflow.LOGGER.info("Setting min. {0} NSM hosts for {1}"
                                     .format(backend['min_nsm_arakoons'], backend['name']))
                ArakoonSetup.checkup_nsm_hosts(albabackend_name=backend['name'],
                                               amount=backend['min_nsm_arakoons'])
                Workflow.LOGGER.info("Finished setting min. {0} NSM hosts for {1}"
                                     .format(backend['min_nsm_arakoons'], backend['name']))

            # Add domains
            Workflow.LOGGER.info("Add domains")
            DomainSetup.link_domains_to_backend(domain_details=backend['domains'], albabackend_name=backend['name'])

            # Add presets
            Workflow.LOGGER.info("Add presets")
            for preset in backend['presets']:
                BackendSetup.add_preset(albabackend_name=backend['name'], preset_details=preset)

            # Link LOCAL backend(s) to GLOBAL backend
            Workflow.LOGGER.info("Link LOCAL backend(s) to GLOBAL backend")
            for subbackend, preset in backend['osds'].iteritems():
                BackendSetup.link_backend(albabackend_name=subbackend, globalbackend_name=backend['name'], preset_name=preset)

        # Setup vpools
        Workflow.LOGGER.info("Setup vpools")
        for storagerouter_ip, storagerouter_details in CIConstants.STORAGEROUTER_INFO.iteritems():
            if 'vpools' not in storagerouter_details:
                continue
            for vpool_name, vpool_details in storagerouter_details['vpools'].iteritems():
                # check if aa is specified
                albabackends = [vpool_details['backend_name']]
                if vpool_details['fragment_cache']['location'] == "backend":
                    albabackends.append(vpool_details['fragment_cache']['backend']['name'])
                # Get amount of proxies
                proxy_amount = vpool_details.get('proxies', 2)
                # create vpool
                VPoolSetup.add_vpool(vpool_name=vpool_name, vpool_details=vpool_details, albabackend_name=albabackends, storagerouter_ip=storagerouter_ip, proxy_amount=proxy_amount)
        # Configure proxies
        for backend in CIConstants.BACKEND_INFO:
            if "proxy" not in backend:
                continue
            ProxySetup.configure_proxy(backend['name'], backend['proxy'])

        Workflow.LOGGER.info("Finished setup")

    def scenario(self, scenarios=None):
        """
        Execute custom scenarios on a Open vStorage environment
        :param scenarios: list of scenarios to execute. Default to the ones specified in the setup.json
        :type scenarios: list[str]
        :return: None
        """
        if scenarios is None or not isinstance(scenarios, list):
            scenarios = self.config['scenarios']
        from ci.autotests import AutoTests
        Workflow.LOGGER.info("Starting scenario's")

        # add possible excluded scenarios
        exclude_scenarios = []
        if 'exclude_scenarios' in self.config:
            exclude_scenarios = self.config['exclude_scenarios']

        print AutoTests.run(scenarios=scenarios, send_to_testrail=self.config['ci'].get('send_to_testrail', False),
                            fail_on_failed_scenario=self.config['ci'].get('fail_on_failed_scenario', False),
                            exclude_scenarios=exclude_scenarios)
        Workflow.LOGGER.info("Finished scenario's")

    def configuration(self):
        """
        Execute custom configurations on a Open vStorage environment

        Documentation:
        https://github.com/openvstorage/framework/blob/5099afe52d67ae72d14286357b7706223c7bfd39/docs/scheduledtasks.md

        :return: None
        """
        if self.config.get('ci', {}).get('configuration', False):
            Workflow.LOGGER.info("Starting configuration")
            if CelerySetup.override_scheduletasks(self.config['configuration']):
                Workflow.LOGGER.info("Finished configuration")
            else:
                Workflow.LOGGER.warning("Failed to configure scheduled tasks")
        else:
            Workflow.LOGGER.info("Skipped configuration")

    def cleanup(self):
        """
        Will fully revert the install. Use if you are sure that a cleanup is required. This will remove all data!
        """
        Workflow.LOGGER.info("Starting removal")
        # Remove vpools
        Workflow.LOGGER.info("Remove vpools")
        for storagerouter_ip, storagerouter_details in CIConstants.STORAGEROUTER_INFO.iteritems():
            if 'vpools' in storagerouter_details:
                for vpool_name, vpool_details in storagerouter_details['vpools'].iteritems():
                    vpool = VPoolHelper.get_vpool_by_name(vpool_name)
                    # Remove the vdisks on the vpool
                    for vdisk_guid in vpool.vdisks_guids:
                        VDiskRemover.remove_vdisk(vdisk_guid=vdisk_guid)
                    VPoolRemover.remove_vpool(vpool_name=vpool_name, storagerouter_ip=storagerouter_ip)
        # Remove backends
        Workflow.LOGGER.info("Remove backends")

        local_backends = []
        global_backends = []
        for backend in CIConstants.BACKEND_INFO:
            if backend['scaling'] == 'LOCAL':
                local_backends.append(backend)
            if backend['scaling'] == 'GLOBAL':
                global_backends.append(backend)

        for local_backend in local_backends:
            # Remove asds
            Workflow.LOGGER.info("Remove asds")
            for storagenode_ip, disks in local_backend['osds'].iteritems():
                BackendRemover.remove_asds(albabackend_name=local_backend['name'], target=storagenode_ip, disks=disks)
        for global_backend in global_backends:
            Workflow.LOGGER.info("unlink local backends")
            for targetbackend_name, preset in global_backend['osds'].iteritems():
                BackendRemover.unlink_backend(globalbackend_name=global_backend['name'], albabackend_name=targetbackend_name)

        # Remove backend
        for backend in local_backends + global_backends:
            Workflow.LOGGER.info("Removing backend {0}".format(backend['name']))
            BackendRemover.remove_backend(albabackend_name=backend['name'])

        # Remove disk roles
        Workflow.LOGGER.info("Remove disk roles")
        for storagerouter_ip, storagerouter_details in CIConstants.STORAGEROUTER_INFO.iteritems():
            for diskname, disk_details in storagerouter_details['disks'].iteritems():
                RoleRemover.remove_role(storagerouter_ip=storagerouter_ip, diskname=diskname)
        Workflow.LOGGER.info("Finished removal")

    @staticmethod
    def main(*args, **kwargs):
        w = Workflow()
        w.run()


if __name__ == "__main__":
    Workflow().setup()
    Workflow().cleanup()
