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
from ci import autotests
from ci.helpers.api import OVSClient
from ci.setup.roles import RoleSetup
from ci.setup.vpool import VPoolSetup
from ci.remove.roles import RoleRemover
from ci.setup.domain import DomainSetup
from ci.setup.arakoon import ArakoonSetup
from ci.setup.backend import BackendSetup
from ovs.log.log_handler import LogHandler
from ci.remove.backend import BackendRemover
from ci.validate.backend import BackendValidation

CONFIG_LOC = "/opt/OpenvStorage/ci/config/setup.json"
TEST_SCENARIO_LOC = "/opt/OpenvStorage/ci/scenarios/"
SETTINGS_LOC = "/opt/OpenvStorage/ci/config/settings.json"
TESTTRAIL_LOC = "/opt/OpenvStorage/ci/config/testtrail.json"


class Workflow(object):

    LOGGER = LogHandler.get(source='workflow', name="ci_workflow")

    def __init__(self, config_path=CONFIG_LOC):
        with open(config_path, "r") as JSON_CONFIG:
            self.config = json.load(JSON_CONFIG)
        self.api = OVSClient(
            self.config['ci']['grid_ip'],
            self.config['ci']['user']['api']['username'],
            self.config['ci']['user']['api']['password']
        )

    def run(self):

        for i in xrange(self.config['ci']['setup_retries']):
            self.setup()
            for j in xrange(self.config['ci']['scenario_retries']):
                self.scenario()
            self.cleanup()

            # if cleanup of items is False, stop another try
            if not self.config['ci']['cleanup']:
                break

    @staticmethod
    def setup_external_arakoons(backend):
        """
        Setup external arakoons for a backend

        :param backend: all backend details
        :type backend: dict
        :return: mapped external arakoons
        :rtype: dict
        """

        # if backend does not exists, deploy the external arakoons
        if not BackendValidation.check_backend(backend_name=backend['name']):
            external_arakoon_mapping = {}
            for ip, arakoons in backend['external_arakoon'].iteritems():
                for arakoon_name, arakoon_settings in arakoons.iteritems():
                    # check if we already created one or not
                    if arakoon_name not in external_arakoon_mapping:
                        # if not created yet, create one and map it
                        external_arakoon_mapping[arakoon_name] = {}
                        external_arakoon_mapping[arakoon_name]['master'] = ip
                        external_arakoon_mapping[arakoon_name]['all'] = [ip]
                        ArakoonSetup.add_arakoon(cluster_name=arakoon_name, storagerouter_ip=ip,
                                                 cluster_basedir=arakoon_settings['base_dir'],
                                                 service_type=arakoon_settings['type'])
                    else:
                        # if created, extend it and map it
                        external_arakoon_mapping[arakoon_name]['all'].append(ip)
                        ArakoonSetup.extend_arakoon(cluster_name=arakoon_name,
                                                    master_storagerouter_ip=
                                                    external_arakoon_mapping[arakoon_name]['master'],
                                                    storagerouter_ip=ip,
                                                    cluster_basedir=arakoon_settings['base_dir'],
                                                    service_type=arakoon_settings['type'],
                                                    clustered_nodes=
                                                    external_arakoon_mapping[arakoon_name]['all'])
            return external_arakoon_mapping
        else:
            Workflow.LOGGER.info("Skipping external arakoon creation because backend `{0}` already exists"
                                 .format(backend['name']))
            return

    def setup(self):
        """
        Setup a Open vStorage cluster based on a config file

        :return: None
        """

        if self.config['ci']['setup']:

            # Start setup
            self.LOGGER.info("Starting setup")

            # Setup domains
            Workflow.LOGGER.info("Setup domains")
            for domain in self.config['setup']['domains']:
                DomainSetup.add_domain(domain, self.api)

            # Setup storagerouter (recovery) domains
            Workflow.LOGGER.info("Setup storagerouter (recovery) domains")
            for storagerouter_ip, storagerouter_details in self.config['setup']['storagerouters'].iteritems():
                DomainSetup.link_domains_to_storagerouter(storagerouter_details['domains'], storagerouter_ip, self.api)

            # Setup disk roles
            Workflow.LOGGER.info("Setup disk roles")
            for storagerouter_ip, storagerouter_details in self.config['setup']['storagerouters'].iteritems():
                for diskname, disk_details in storagerouter_details['disks'].iteritems():
                    RoleSetup.add_disk_role(storagerouter_ip=storagerouter_ip, diskname=diskname, roles=disk_details['roles'],
                                            api=self.api)

            # Setup LOCAL backends
            Workflow.LOGGER.info("Setup `LOCAL` backends")
            for backend in self.config['setup']['backends']:
                if backend['scaling'] == "LOCAL":
                    # check if possibly we need to setup external arakoons
                    if 'external_arakoon' in backend:
                        Workflow.LOGGER.info("Add external arakoons")
                        self.setup_external_arakoons(backend)
                        Workflow.LOGGER.info("Finished adding external arakoons")

                    BackendSetup.add_backend(backend_name=backend['name'], api=self.api, scaling="LOCAL")

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
                    DomainSetup.link_domains_to_backend(domain_details=backend['domains'],
                                                        albabackend_name=backend['name'], api=self.api)

                    # Add presets
                    Workflow.LOGGER.info("Add presets")
                    for preset in backend['presets']:
                        BackendSetup.add_preset(albabackend_name=backend['name'], preset_details=preset, api=self.api)

                    # Initialize and claim asds
                    Workflow.LOGGER.info("Initialize and claim asds")
                    for storagenode_ip, disks in backend['osds'].iteritems():
                        BackendSetup.add_asds(albabackend_name=backend['name'], target=storagenode_ip, disks=disks,
                                              api=self.api)
                else:
                    pass

            # Setup GLOBAL backends
            Workflow.LOGGER.info("Setup `GLOBAL` backends")
            for backend in self.config['setup']['backends']:
                if backend['scaling'] == "GLOBAL":
                    # check if possibly we need to setup external arakoons
                    if 'external_arakoon' in backend:
                        Workflow.LOGGER.info("Add external arakoons")
                        self.setup_external_arakoons(backend)
                        Workflow.LOGGER.info("Finished adding external arakoons")

                    BackendSetup.add_backend(backend_name=backend['name'], api=self.api, scaling="GLOBAL")

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
                    DomainSetup.link_domains_to_backend(domain_details=backend['domains'],
                                                        albabackend_name=backend['name'], api=self.api)

                    # Add presets
                    Workflow.LOGGER.info("Add presets")
                    for preset in backend['presets']:
                        BackendSetup.add_preset(albabackend_name=backend['name'], preset_details=preset, api=self.api)

                    # Link LOCAL backend(s) to GLOBAL backend
                    Workflow.LOGGER.info("Link LOCAL backend(s) to GLOBAL backend")
                    for subbackend, preset in backend['osds'].iteritems():
                        BackendSetup.link_backend(albabackend_name=subbackend, globalbackend_name=backend['name'],
                                                  preset_name=preset, api=self.api)
                else:
                    continue

            # Setup vpools
            Workflow.LOGGER.info("Setup vpools")
            for storagerouter_ip, storagerouter_details in self.config['setup']['storagerouters'].iteritems():
                if 'vpools' in storagerouter_details:
                    for vpool_name, vpool_details in storagerouter_details['vpools'].iteritems():
                        # check if aa is specified
                        albabackends = [vpool_details['backend_name']]
                        if vpool_details['fragment_cache']['location'] == "backend":
                            albabackends.append(vpool_details['fragment_cache']['backend']['name'])

                        # create vpool
                        VPoolSetup.add_vpool(vpool_name=vpool_name, vpool_details=vpool_details, api=self.api,
                                             albabackend_name=albabackends,
                                             storagerouter_ip=storagerouter_ip)
                else:
                    continue
            Workflow.LOGGER.info("Finished setup")
        else:
            Workflow.LOGGER.info("Skipped setup")

    def scenario(self):
        """
        Execute custom scenarios on a Open vStorage environment

        :return: None
        """
        if self.config['ci']['scenarios']:
            Workflow.LOGGER.info("Starting scenario's")
            print autotests.run(scenarios=self.config['scenarios'],
                                send_to_testrail=self.config['ci']['send_to_testrail'],
                                fail_on_failed_scenario=self.config['ci']['fail_on_failed_scenario'])
            Workflow.LOGGER.info("Finished scenario's")
        else:
            Workflow.LOGGER.info("Skipped scenario's")

    def cleanup(self):
        if self.config['ci']['cleanup']:
            Workflow.LOGGER.info("Starting removal")
            # Remove vpools
            Workflow.LOGGER.info("Remove vpools")
            for storagerouter_ip, storagerouter_details in self.config['setup']['storagerouters'].iteritems():
                if 'vpools' in storagerouter_details:
                    for vpool_name, vpool_details in storagerouter_details['vpools'].iteritems():
                        pass

            # Remove backends
            Workflow.LOGGER.info("Remove backends")
            for backend in self.config['setup']['backends']:

                # Remove asds
                Workflow.LOGGER.info("Remove asds")
                for storagenode_ip, disks in backend['osds'].iteritems():
                    BackendRemover.remove_asds(albabackend_name=backend['name'], target=storagenode_ip, disks=disks,
                                               api=self.api)

                # Remove backend
                Workflow.LOGGER.info("Remove backend")
                pass

            # Remove disk roles
            Workflow.LOGGER.info("Remove disk roles")
            for storagerouter_ip, storagerouter_details in self.config['setup']['storagerouters'].iteritems():
                for diskname, disk_details in storagerouter_details['disks'].iteritems():
                    RoleRemover.remove_role(ip=storagerouter_ip, diskname=diskname, api=self.api)
            Workflow.LOGGER.info("Finished removal")
        else:
            Workflow.LOGGER.info("Skipped removal")

    @staticmethod
    def main(*args, **kwargs):
        w = Workflow()
        w.run()

if __name__ == "__main__":
    Workflow.main()



