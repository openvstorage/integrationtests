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
OVS automatic test lib
"""
import os
import re
import json
import math
import importlib
import subprocess
from datetime import datetime
from ovs.extensions.generic.system import System

from ci.api_lib.helpers.exceptions import SectionNotFoundError
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.testrailapi import TestrailApi, TestrailCaseType, TestrailResult
from ci.main import CONFIG_LOC
from ovs.extensions.generic.logger import Logger


class AutoTests(object):

    logger = Logger("autotests-ci_autotests")
    TEST_SCENARIO_LOC = "/opt/OpenvStorage/ci/scenarios/"
    TESTTRAIL_LOC = "/opt/OpenvStorage/ci/config/testrail.json"
    EXCLUDE_FLAG = "-exclude"
    with open(CONFIG_LOC, 'r') as config_file:
        CONFIG = json.load(config_file)

    @staticmethod
    def run(scenarios=None, send_to_testrail=False, fail_on_failed_scenario=False, only_add_given_results=True, exclude_scenarios=None):
        """
        Run single, multiple or all test scenarios
        :param scenarios: run scenarios defined by the test_name, leave empty when ALL test scenarios need to be executed (e.g. ['ci.scenarios.alba.asd_benchmark', 'ci.scenarios.arakoon.collapse'])
        :type scenarios: list
        :param exclude_scenarios: exclude scenarios defined by the test_name (e.g. when scenarios=['ALL'] is specified, you can exclude some tests)
        :type scenarios: list
        :param send_to_testrail: send results of test to testrail in a new testplan
        :type send_to_testrail: bool
        :param fail_on_failed_scenario: the run will block all other tests if one scenario would fail
        :type fail_on_failed_scenario: bool
        :param only_add_given_results: ONLY ADD the given cases in results
        :type only_add_given_results: bool
        :returns: results and possible testrail url
        :rtype: tuple
        """
        logger = AutoTests.logger
        if scenarios is None:
            scenarios = ['ALL']
        if exclude_scenarios is None:
            exclude_scenarios = AutoTests.CONFIG.get('exclude_scenarios', [])
        logger.info("Collecting tests.")  # Grab the tests to execute
        tests = [autotest for autotest in AutoTests.list_tests(scenarios[:]) if autotest not in exclude_scenarios]  # Filter out tests with EXCLUDE_FLAG
        # print tests to be executed
        logger.info("Executing the following tests: {0}".format(tests))
        # execute the tests
        logger.info("Starting tests.")
        results = {}
        blocked = False
        for test in tests:
            mod = importlib.import_module('{0}.main'.format(test))
            module_result = mod.run(blocked)
            if hasattr(TestrailResult, module_result['status']):  # check if a test has failed, if it has failed check if we should block all other tests
                if getattr(TestrailResult, module_result['status']) == TestrailResult.FAILED and fail_on_failed_scenario:
                    if 'blocking' not in module_result:
                        blocked = True  # if a test reports failed but blocked is not present = by default blocked == True
                    elif module_result['blocking'] is not False:
                        blocked = True  # if a test reports failed but blocked != False
            else:
                raise AttributeError("Attribute `{0}` does not exists as status in TestrailResult".format(module_result['status']))
            # add test to results & also remove possible EXCLUDE_FLAGS on test name
            results[test.replace(AutoTests.EXCLUDE_FLAG, '')] = module_result
        logger.info("Finished tests.")
        if send_to_testrail:
            logger.info("Start pushing tests to testrail.")
            plan_url = AutoTests.push_to_testrail(results, only_add_given_cases=only_add_given_results)
            return results, plan_url
        return results, None

    @staticmethod
    def list_tests(cases=None, exclude=None, start_dir=TEST_SCENARIO_LOC, categories=None, subcategories=None, depth=1):
        """
        Lists the requested test scenarios
        :returns: all available test scenarios
        :rtype: list
        """
        if exclude is None:
            exclude = [AutoTests.EXCLUDE_FLAG, '.pyc']
        depth_root = '/opt/OpenvStorage/'
        if cases is None:
            cases = ['ALL']
        if isinstance(cases, str):
            cases = [cases]
        if not isinstance(cases, list):
            raise TypeError('The cases argument is of type {0}, expected a list or a string'.format(type(cases)))
        elif subcategories is None and categories is None:
            categories = []
            subcategories = []
            for index, case in enumerate(cases[:]):  # split
                split_entry = case.split('.')
                if len(split_entry) >= 3:
                    cases.remove(case)  # Instead of pop to remove the index error
                    categories.append(split_entry[2])
                if len(case.split('.')) >= 4:
                    subcategories.append(split_entry[3])
        # Depth meaning: 1 -> category of tests 2: -> subcategory of tests further: -> expected main.py or unexplored
        # collect sections
        entries = os.listdir(start_dir)
        # collect tests/scenarios under sections
        scenarios = []
        for entry in entries:
            current_path = os.path.join(start_dir, entry)
            current_depth = depth
            if entry == 'example' or entry.startswith('__init__.py') or entry.endswith(tuple(exclude)):
                continue
            if depth == 1:
                if not (os.path.basename(current_path) in categories or len(categories) == 0):
                    continue
            elif depth == 2:
                if not (os.path.basename(current_path) in subcategories or len(subcategories) == 0):
                    continue
            # If all entries are directories -> go deeper
            if os.path.isdir(current_path):
                scenarios.extend(AutoTests.list_tests(cases[:], exclude, current_path, categories, subcategories, current_depth + 1))
            else:
                scenario = start_dir.replace(depth_root, '').replace('/', '.')
                if len(cases) == 0 or cases == ['ALL'] or scenario in cases:
                    scenarios.append(scenario)
        return scenarios

    @staticmethod
    def push_to_testrail(results, config_path=TESTTRAIL_LOC, skip_on_no_results=True, only_add_given_cases=False):
        """
        Push results to testtrail
        :param config_path: path to testrail config file
        :type config_path: str
        :param results: tests and results of test (e.g {'ci.scenarios.arakoon.collapse': {'status': 'FAILED'}, 'ci.scenarios.arakoon.archive': {'status': 'PASSED'}})
        :type results: dict
        :param skip_on_no_results: set the untested tests on SKIPPED
        :type skip_on_no_results: bool
        :param only_add_given_cases: ONLY ADD the given cases in results
        :type only_add_given_cases: bool
        :return: Testrail URL to test plan
        :rtype: str
        """
        logger = AutoTests.logger
        logger.info("Pushing tests to testrail ...")
        with open(config_path, "r") as JSON_CONFIG:
                testtrail_config = json.load(JSON_CONFIG)

        # fetch test-name based on environment, environment version & datetime
        test_title = "{0}_{1}_{2}".format(AutoTests._get_test_name(), AutoTests._get_ovs_version(), datetime.now())

        # create description based on system settings (hardware & linux distro)
        description = AutoTests._get_description()

        # setup testrail api connection
        if not testtrail_config['url']:
            raise RuntimeError("Invalid url for testrail")

        if not testtrail_config['key']:
            # no key provided so we will continue with username & password
            if not testtrail_config['username'] and testtrail_config['password']:
                raise RuntimeError("Invalid username or password specified for testrail")
            else:
                tapi = TestrailApi(server=testtrail_config['url'], user=testtrail_config['username'], password=testtrail_config['password'])
        else:
            tapi = TestrailApi(testtrail_config['url'], key=testtrail_config['key'])

        project_id = tapi.get_project_by_name(testtrail_config['project'])['id']
        suite_id = tapi.get_suite_by_name(project_id, testtrail_config['suite'])['id']

        # check if test_case & test_section exists in test_suite
        for test_case, test_result in results.iteritems():
            test_name = test_case.split('.')[3]
            test_section = test_case.split('.')[2].capitalize()
            try:
                tapi.get_case_by_name(project_id, suite_id, test_name)
            except Exception:
                # check if section exists
                try:
                    section = tapi.get_section_by_name(project_id, suite_id, test_section)
                except Exception:
                    raise SectionNotFoundError("Section `{0}` is not available in testrail, please add or correct your mistake.".format(test_section))

                if hasattr(TestrailCaseType, test_result['case_type']):
                    case_type_id = tapi.get_case_type_by_name(getattr(TestrailCaseType, test_result['case_type']))['id']
                else:
                    raise AttributeError("Attribute `{0}` does not exists as case_type "
                                         "in TestrailCaseType".format(test_result['case_type']))
                # add case to existing section
                tapi.add_case(section_id=section['id'], title=test_name, type_id=case_type_id)

        # add plan
        plan = tapi.add_plan(project_id, test_title, description)
        # link suite to plan

        if not only_add_given_cases:
            # add all tests to the test_suite, regardless of execution
            entry = tapi.add_plan_entry(plan['id'], suite_id, testtrail_config['suite'])
        else:
            # collect case_ids of executed tests
            executed_case_ids = []
            for test_case in results.iterkeys():
                section_id = tapi.get_section_by_name(project_id, suite_id, test_case.split('.')[2].capitalize().strip())['id']
                executed_case_ids.append(tapi.get_case_by_name(project_id=project_id, suite_id=suite_id,
                                                               name=test_case.split('.')[3], section_id=section_id)['id'])
            # only add tests to test_suite that have been executed
            entry = tapi.add_plan_entry(plan['id'], suite_id, testtrail_config['suite'], case_ids=executed_case_ids,
                                        include_all=False)

        # add results to test cases
        run_id = entry['runs'][0]['id']
        for test_case, test_result in results.iteritems():
            # check if test exists
            test_name = test_case.split('.')[3]
            test_id = tapi.get_test_by_name(run_id, test_name)['id']

            if hasattr(TestrailResult, test_result['status']):
                test_status_id = getattr(TestrailResult, test_result['status'])
            else:
                raise AttributeError("Attribute `{0}` does not exists as test_status in TestrailResult"
                                     .format(test_result['status']))
            # add results to test cases, if the've got something in the field `errors`
            if test_result['errors'] is not None:
                tapi.add_result(test_id, test_status_id, comment=str(test_result['errors']))
            else:
                tapi.add_result(test_id, test_status_id)

        # end of adding results to testplan, setting other cases in SKIPPED
        if skip_on_no_results:
            for test in tapi.get_tests(run_id):
                if test['status_id'] == TestrailResult.UNTESTED:
                    tapi.add_result(test['id'], int(TestrailResult.SKIPPED))

        logger.info("Finished pushing tests to testrail ...")
        return plan['url']

    @staticmethod
    def _get_package_info():
        """
        Retrieve package information for installation
    
        :returns: package information of openvstorage, volumedriver, alba, arakoon & python-celery
        :rtype: str
        """
        command = "dpkg-query -W -f='${binary:Package} ${Version}\t${Description}\n' " \
                  "| grep '^openvstorage\|^volumedriver\|^alba\|^arakoon\|^python-celery'"

        child_process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)

        (output, _error) = child_process.communicate()
        return output

    @staticmethod
    def _get_test_name():
        """
        Retrieve a structured environment test name
    
        :returns: a structured environment based test name
        :rtype: str
        """
        number_of_nodes = len(StoragerouterHelper.get_storagerouters())
        split_ip = System.get_my_storagerouter().ip.split('.')
        return str(number_of_nodes) + 'N-' + split_ip[2] + '.' + split_ip[3]

    @staticmethod
    def _get_ovs_version():
        """
        Retrieve version of ovs installation
    
        :returns: openvstorage package version
        :rtype: str
        """
        packages = AutoTests._get_package_info()
        main_pkg = [pck for pck in packages.splitlines() if "openvstorage " in pck]
        if not main_pkg:
            return ""

        return re.split("\s*", main_pkg[0])[1]

    @staticmethod
    def _get_description():
        """
        Retrieve extensive information about the machine
    
        :returns: a extensive description of the local machine
        :rtype: str
        """
        description_lines = []
        # fetch ip information
        description_lines.append('# IP INFO')
        for ip in StoragerouterHelper.get_storagerouter_ips():
            description_lines.append('* {0}'.format(ip))
        description_lines.append('')  # New line gap
        # hypervisor information
        with open(CONFIG_LOC, "r") as JSON_CONFIG:
                ci_config = json.load(JSON_CONFIG)
        description_lines.append('# HYPERVISOR INFO')
        description_lines.append('{0}'.format(ci_config['ci']['local_hypervisor']['type']))
        description_lines.append('')  # New line gap
        # fetch hardware information
        description_lines.append("# HARDWARE INFO")
        # board information
        description_lines.append("### Base Board Information")
        description_lines.append("{0}".format(subprocess.check_output("dmidecode -t 2", shell=True).replace("#", "").strip()))
        description_lines.append('')  # New line gap
        # fetch cpu information
        description_lines.append("### Processor Information")
        output = subprocess.Popen("grep 'model name'", stdin=subprocess.Popen("cat /proc/cpuinfo", stdout=subprocess.PIPE, shell=True).stdout, stdout=subprocess.PIPE, shell=True)
        cpus = subprocess.check_output("cut -d ':' -f 2", stdin=output.stdout, shell=True).strip().split('\n')
        description_lines.append("* Type: {0}".format(cpus[0]))
        description_lines.append("* Amount: {0}".format(len(cpus)))
        description_lines.append('')  # New line gap
        # fetch memory information
        description_lines.append("### Memory Information")
        output = math.ceil(float(subprocess.check_output("grep MemTotal", stdin=subprocess.Popen("cat /proc/meminfo", stdout=subprocess.PIPE, shell=True).stdout, shell=True).strip().split()[1]) / 1024 / 1024)
        description_lines.append("* {0}GiB System Memory".format(int(output)))
        description_lines.append('')  # New line gap
        # fetch disk information
        description_lines.append("### Disk Information")
        output = subprocess.check_output("lsblk", shell=True)
        description_lines.append(output.strip())
        description_lines.append('')  # New line gap
        # package info
        description_lines.append("# PACKAGE INFO")
        description_lines.append("{0}".format(AutoTests._get_package_info()))

        return '\n'.join(description_lines)


class LogCollector(object):
    """
    Exposes to methods to collect logs
    """
    DEFAULT_COMPONENTS = [{'framework': ['ovs-workers']}, 'volumedriver']
    COMPONENT_MAPPING = {'framework': ['ovs-workers', 'ovs-webapp-api'],
                         'arakoon': ['ovs-arakoon-*-abm', 'ovs-arakoon-*-nsm', 'ovs-arakoon-config'],
                         'alba': ['ovs-albaproxy_*'],
                         'volumedriver': ['ovs-volumedriver_*']}

    @staticmethod
    def get_logs(components=None, since=None, until=None, auto_complete=True):
        """
        Get logs for specified components
        :param components: list of components. Can be strings or dicts to specify which logs
        :type components: list[str] / list[dict]
        :param since: start collecting logs from this timestamp
        :type since: str / DateTime
        :param until: stop collecting when this timestamp is found
        :type until: str / DateTime
        :param auto_complete: replaced * with found entries, works around the journalctl flaw
        :type auto_complete: bool
        :return: all logs for the components listed
        :rtype: str
        """
        logger = AutoTests.logger
        logger.debug('Grepping logs between {0} and {1}.'.format(since, until))
        from ovs_extensions.log.log_reader import LogFileTimeParser
        if components is None:
            components = LogCollector.DEFAULT_COMPONENTS
        units = []
        mapping = LogCollector.COMPONENT_MAPPING
        for component in components:
            if isinstance(component, str):
                if component not in mapping:
                    raise KeyError('{0} cannot be found in the mapping. Available options are: {1}'.format(component, mapping.keys()))
            if isinstance(component, dict):
                for key in component.keys():
                    if key not in mapping:
                        raise KeyError('{0} cannot be found in the mapping. Available options are: {1}'.format(component, mapping.keys()))
            if isinstance(component, str):
                # All options
                units.extend(mapping[component])
            elif isinstance(component, dict):
                # Query options
                for compent_key, requested_units in component.iteritems():
                    filters = [item.split('*')[0] for item in mapping[compent_key]]
                    matched = [item for item in requested_units if item.startswith(tuple(filters))]
                    if len(matched) == 0:
                        raise ValueError('Could not match the following components: [0]. Consider the following prefixes: [1]'.format(requested_units, filters))
                    units.extend(matched)
        if auto_complete is True:
            from ovs.extensions.services.servicefactory import ServiceFactory
            from ovs.extensions.generic.system import System
            from ovs.extensions.generic.sshclient import SSHClient
            service_manager = ServiceFactory.get_manager()
            found_services = [service for service in service_manager.list_services(SSHClient(System.get_my_storagerouter()))]
            completed_units = []
            for item in units:
                services = [service_name for service_name in found_services if service_name.startswith(item.split('*')[0])]
                found_services = list(set(found_services) - set(services))
                completed_units.extend(services)
            units = completed_units
        units = ['{0}.service'.format(unit) for unit in units[:]]  # append .service
        logger.debug('Grepping logs for the following units: {0} between {1} and {2}.'.format(units, since, until))
        return LogFileTimeParser.execute_search_on_remote(since=since, until=until, search_locations=units)


def gather_results(case_type, logger, test_name, log_components=None):
    """
    Result gathering to be used as decorator for the autotests
    Gathers the logs when the test has failed and will push these to testrail
    Must be put on the main method of every class that is part of the suite
    Replaces: 
        if not blocked:
            try:
                HATester._execute_test()
                return {'status': 'PASSED', 'case_type': HATester.CASE_TYPE, 'errors': None}
            except Exception as ex:
                return {'status': 'FAILED', 'case_type': HATester.CASE_TYPE, 'errors': str(ex), 'blocking': False}
        else:
            return {'status': 'BLOCKED', 'case_type': HATester.CASE_TYPE, 'errors': None}
    from the main method
    Now it becomes
        @gather_results(CASE_TYPE, logger, TEST_NAME)
        def main(blocked):
    :param case_type: case type specified in the main already
    :type case_type: str
    :param logger: logger instance specified already
    :type logger: ovs.log.log_handler.LogHandler
    :param test_name: name of the test(most likely name of the logger)
    :type test_name: str
    :param log_components: components to fetch logging from when the test would fail
    :type log_components: list
    :return: 
    """
    import inspect
    import datetime

    def wrapper(func):
        def wrapped(*args, **kwargs):
            start = datetime.datetime.now()
            try:
                func_args = inspect.getargspec(func)[0]
                try:
                    blocked_index = func_args.index('blocked')  # Expect blocked
                except ValueError:
                    raise ValueError('Expected argument blocked but failed to retrieve it.')
                blocked = kwargs.get('blocked', None)
                if kwargs.get('blocked') is None:  # in args
                    blocked = args[blocked_index]
                if blocked is True:
                    return {'status': 'BLOCKED', 'case_type': case_type, 'errors': None}
                result = func(*args, **kwargs)  # Execute the method
                return {'status': 'PASSED', 'case_type': case_type, 'errors': result}
            except Exception as ex:
                end = datetime.datetime.now()
                result = [str(ex), '', 'Logs collected between {0} and {1}'.format(start, end), '', LogCollector.get_logs(components=log_components, since=start, until=end)]
                logger.exception('Test {0} has failed with error: {1}.'.format(test_name, str(ex)))
                return {'status': 'FAILED', 'case_type': case_type, 'errors': '\n'.join(result), 'blocking': False}
        return wrapped
    return wrapper
