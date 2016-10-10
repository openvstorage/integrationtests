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
from ci.helpers.api import OVSClient
from ci.setup.roles import RoleSetup
from ci.setup.vpool import VPoolSetup
from ci.setup.domain import DomainSetup
from ci.setup.backend import BackendSetup
from ovs.log.log_handler import LogHandler
from ci.remove.backend import BackendRemover

CONFIG_LOC = "/opt/OpenvStorage/ci/config/setup.json"


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

    def setup(self):

        if self.config['ci']['setup']:

            # Start setup
            self.LOGGER.info("Start setup")

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
                    RoleSetup.add_disk_role(ip=storagerouter_ip, diskname=diskname, roles=disk_details['roles'],
                                            api=self.api)

            # Setup LOCAL backends
            Workflow.LOGGER.info("Setup `LOCAL` backends")
            for backend in self.config['setup']['backends']:
                if backend['scaling'] == "LOCAL":
                    BackendSetup.add_backend(backend_name=backend['name'], api=self.api, scaling="LOCAL")

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
                                              scaling=backend['scaling'], api=self.api)
                else:
                    pass

            # Setup GLOBAL backends
            Workflow.LOGGER.info("Setup `GLOBAL` backends")
            for backend in self.config['setup']['backends']:
                if backend['scaling'] == "GLOBAL":
                    BackendSetup.add_backend(backend_name=backend['name'], api=self.api, scaling="GLOBAL")

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
                        VPoolSetup.add_vpool(vpool_name, vpool_details, self.api,
                                             albabackend_name=albabackends,
                                             storagerouter_ip=storagerouter_ip)
                else:
                    continue
        else:
            # Skipping setup
            Workflow.LOGGER.info("Skipping setup")

    def validate(self):
        pass

    def scenario(self):
        pass

    def cleanup(self):
        if self.config['ci']['cleanup']:
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
                    BackendRemover.remove_asds(albabackend_name=backend['name'], target=storagenode_ip, disks=disks, scaling=backend['scaling'], api=self.api)

                # Remove backend
                Workflow.LOGGER.info("Remove backend")
                pass

            # Remove disk roles
            Workflow.LOGGER.info("Remove disk roles")
            for storagerouter_ip, storagerouter_details in self.config['setup']['storagerouters'].iteritems():
                for diskname, disk_details in storagerouter_details['disks'].iteritems():
                    pass

    @staticmethod
    def main(*args, **kwargs):
        w = Workflow()
        w.setup()
        w.validate()
        w.scenario()
        # w.cleanup()

if __name__ == "__main__":
    Workflow.main()



