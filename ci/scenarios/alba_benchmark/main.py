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
import subprocess
import csv
import json
from ovs.log.log_handler import LogHandler
from ci.setup.backend import BackendSetup
from ci.helpers.api import OVSClient
from ci.remove.backend import BackendRemover

"""
THIS IS NOT A VALID SCENARIO AS OF YET
CAUTION WHEN REPRODUCING BASED OF THIS
A QUICK BENCHMARK WAS REQUIRED AND THIS WAS THE EASIEST WAY OF DOING IT BUT IT BREAKS ALL OUR SEPERATION LOGIC THAT WE
STRIFE FOR

DO NOT USE AS AN EXAMPLE!!!!!!!!!!!!
"""


class AlbaBenchmark(object):
    
    LOGGER = LogHandler.get(source='workflow', name="ci_workflow")
    STANDARD_NUMBER_OF_ASDS = 6
    NUMBER_OF_CLIENTS = 16
    NUMBER_OF_VPOOLS = 16
    # Defaults to 10.000 if not specified
    NUMBER_OF_UPLOADS = 1000
    OUTPUT_FILE = '/tmp/output_bench'
    OUTPUT_CSV = '/tmp/output_csv_{0}'
    CONFIG_LOCATION = 'arakoon://config/ovs/arakoon/mybackend-abm/config?ini=%2Fopt%2FOpenvStorage%2Fconfig%2Farakoon_cacc.ini'
    NAMESPACE = 'mybackend-ns'
    # Default to 32mb
    FILE_SIZE = '32'
    SCENARIOS = ['writes', 'partial-reads']

    # Keep track of amount of testing iterations:
    test_iteration = 0

    def __init__(self, config_path="/opt/OpenvStorage/ci/config/alba_bench.json"):
        with open(config_path, "r") as JSON_CONFIG:
            self.config = json.load(JSON_CONFIG)
        self.api = OVSClient(
            self.config['ci']['grid_ip'],
            self.config['ci']['user']['api']['username'],
            self.config['ci']['user']['api']['password']
        )

    @staticmethod
    def _process_test_results():
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter
        :return:
        """
        pass

    @staticmethod
    def _push_to_testrail():
        """
        Required method that has to follouw our testrail pushing guidelines
        Will send the data to testrail
        :return:
        """

    @staticmethod
    def parse_duration(duration_list):
        # average of all durations for every client
        return sum(AlbaBenchmark.parse_float(item) for item in duration_list)/len(duration_list)

    @staticmethod
    def parse_data_per_second(data_list):
        # Add up all the data
        return sum(AlbaBenchmark.parse_float(item) for item in data_list)

    @staticmethod
    def parse_float(string):
        try:
            return float(string)
        except ValueError:
            return None

    @staticmethod
    def convert_results(number_of_asds, number_of_clients, scenarios, csv_file, number_of_vpools, number_of_uploads, file_size):
        test_results = {}
        current_scenario = None
        for scenario in scenarios:
            test_results[scenario] = {}
            test_results[scenario]['seconds_list'] = []
            test_results[scenario]['data_per_second_list'] = []
        with open(AlbaBenchmark.OUTPUT_FILE, 'r') as f:
            all_lines = f.readlines()
            for line in all_lines:
                if 'Starting scenario' in line:
                    current_scenario = line.split()[2]
                if 'took:' in line:
                    split_entry = line.split()
                    if current_scenario is not None:
                        test_results[current_scenario]['seconds_list'].append(split_entry[1][:-1])
                        test_results[current_scenario]['data_per_second_list'].append(split_entry[3][1:])
                    else:
                        print 'Found results but no scenario, something went wrong during parsing'
        print test_results
        for scenario in scenarios:
            if scenario == 'writes':
                with open(csv_file.format(scenario), 'ab+') as csvfile:
                    writer = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_ALL)
                    if '"number_of_asds","amount_of_vpools","average_duration","data_per_second"' not in csvfile.readline().rstrip():
                        #Csv header not present
                        writer.writerow(['number_of_asds', 'amount_of_vpools', 'average_duration', 'data_per_second', 'number_of_uploads', 'file_size'])
                    amount_of_vpools = 1
                    # Length of both lists should be identical
                    print len(test_results[scenario]['seconds_list'])
                    for i in xrange(AlbaBenchmark.test_iteration * number_of_clients * number_of_vpools, len(test_results[scenario]['seconds_list']), number_of_clients):
                        average_duration =AlbaBenchmark.parse_duration(test_results[scenario]['seconds_list'][i:i + number_of_clients])
                        data_per_second = AlbaBenchmark.parse_data_per_second(test_results[scenario]['data_per_second_list'][i:i + number_of_clients])
                        writer.writerow([number_of_asds, amount_of_vpools, average_duration, data_per_second, number_of_uploads, file_size])
                        # Every hop means an increasing amount of vpools
                        amount_of_vpools += 1

        AlbaBenchmark.test_iteration += 1

    @staticmethod
    def start_tests(test_file, output_file, config_location, namespace, number_of_clients, number_of_vpools, scenarios, number_of_uploads):
        for scenario in scenarios:
            # csv_file is bound to the scenario

            subprocess.check_output('echo "Starting scenario {0}" >> {1}'.format(scenario, output_file), shell=True)
            for number_of_vpools in xrange(1, number_of_vpools +1):
                # Check namespaces - must be remade every test iteration
                print "Deleting namespace"
                subprocess.check_output('alba delete-namespace {0} --config={1}'.format(AlbaBenchmark.NAMESPACE, config_location), shell=True)
                print "Creating namespace"
                subprocess.check_output('alba create-namespace {0} --config={1}'.format(AlbaBenchmark.NAMESPACE, config_location), shell=True)
                if scenario == 'writes':
                    subprocess.check_output(
                        'for x in {{1..{0}}}; do alba alba-bench --config={1} --file {2} --scenario {3} --n-clients {4} -n {7} --robust --prefix $x {5} >> {6}; done'.format(
                            number_of_vpools, config_location, test_file, scenario,
                            number_of_clients, namespace, output_file, number_of_uploads),
                        shell=True
                    )
                else:
                    # Implement partial-reads logic
                    pass

    def main(self, max_asds=STANDARD_NUMBER_OF_ASDS, output_file=OUTPUT_FILE, config_location=CONFIG_LOCATION, file_size=FILE_SIZE, namespace=NAMESPACE,
                    number_of_clients=NUMBER_OF_CLIENTS, number_of_vpools=NUMBER_OF_VPOOLS, scenarios=SCENARIOS, csv_file=OUTPUT_CSV, number_of_uploads=NUMBER_OF_UPLOADS):

        # Clean temp files
        with open(output_file, 'w'):
            pass
        for scenario in scenarios:
            with open(csv_file.format(scenario), 'w'):
                pass
        # Delete old filesize
        test_file = '/tmp/{0}MB.bin'.format(file_size)
        subprocess.check_output('rm -rf {0}'.format(test_file), shell=True)
        # Create filesize
        subprocess.check_output('dd if=/dev/urandom of={0} bs={1}M count=1'.format(test_file, file_size), shell=True)
        # Setup a normal flow up to claiming of asds - see json
        # CURRENTLY USING FLOW CODE TO MINIMIZE WORK - WOULD REQUIRE SKIPS FOR THIS TEST TO PROCESS CORRECTLY
        for number_of_asds in xrange(1, max_asds +1):
            # Setup backends
            AlbaBenchmark.LOGGER.info("Setup backends")
            for backend in self.config['setup']['backends']:
                # BackendSetup.add_backend(backend_name=backend['name'], api=self.api, scaling=backend['scaling'])

                # Add presets
                AlbaBenchmark.LOGGER.info("Add presets")
                # for preset in backend['presets']:
                #     BackendSetup.add_preset(albabackend_name=backend['name'], preset_details=preset, api=self.api)

                # Initialize and claim asds
                AlbaBenchmark.LOGGER.info("Initialize and claim asds")
                for storagenode_ip, disks in backend['osds'].iteritems():
                    BackendSetup.add_asds(albabackend_name=backend['name'], target=storagenode_ip, disks=disks,
                                          scaling=backend['scaling'], api=self.api)

            # Start benchmark
            AlbaBenchmark.start_tests(output_file=output_file, config_location=config_location, test_file=test_file, namespace=namespace,
                                      number_of_clients=number_of_clients, number_of_vpools=number_of_vpools,
                                      scenarios=scenarios, number_of_uploads=number_of_uploads)
            AlbaBenchmark.convert_results(number_of_vpools=number_of_vpools, number_of_asds=number_of_asds,
                                          number_of_clients=number_of_clients, scenarios=scenarios, csv_file=csv_file,
                                          number_of_uploads=number_of_uploads, file_size=file_size)

            # Remove backends
            AlbaBenchmark.LOGGER.info("Remove backends")
            for backend in self.config['setup']['backends']:

                # Remove asds and initialized disks
                AlbaBenchmark.LOGGER.info("Remove asds")
                for storagenode_ip, disks in backend['osds'].iteritems():
                    BackendRemover.remove_asds(albabackend_name=backend['name'], target=storagenode_ip,
                                               disks=disks, scaling=backend['scaling'], api=self.api)

            # Edit values to continue the test
            for backend in self.config['setup']['backends']:
                for storagenode_ip, disks in backend['osds'].iteritems():
                    for disk, amount_of_osds in disks.iteritems():
                        self.config['setup']['backends'][self.config['setup']['backends'].index(backend)]['osds'][storagenode_ip][disk] = amount_of_osds +1

    @staticmethod
    def benchmark_searching():
        # Proved Kenneth wrong!
        test_list = []
        for i in xrange(1, 10000000):
            if i % 5 == 0:
                test_list.append('took: 10.110722s or (61.815565 /s)')
            else:
                test_list.append('randomgibberish that is same size')
        # Searching
        import time
        import re
        start = time.time()
        seconds_list = []
        data_list = []
        for entry in test_list:
            if 'took:' in entry:
                split_entry = entry.split()
                seconds_list.append(split_entry[1][:-1])
                data_list.append(split_entry[3][1:])
        stop = time.time()
        took = stop - start
        print took
        # 3x slower than above
        start = time.time()
        seconds_list = []
        data_list = []
        r = re.compile('took: (\d+\.\d+)s or \((\d+\.\d+) ')
        for entry in test_list:
            m = r.match(entry)
            if m is not None:
                d = m.groups()
                seconds_list.append(d[0])
                data_list.append(d[1])
        stop = time.time()
        took = stop - start
        print took

if __name__ == "__main__":
    AlbaBenchmark().main()
