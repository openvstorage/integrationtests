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

import base64
import requests
import urllib2


class TestrailResult:
    """
    Testrail Result class
    """

    PASSED = 1
    BLOCKED = 2
    FAILED = 5
    SKIPPED = 11
    UNTESTED = 3


class TestrailPriority(object):
    """
    Testrail Priority class
    """

    MUST_TEST_HIGH = 5
    MUST_TEST_LOW = 4
    TEST_IF_TIME_HIGH = 3
    TEST_IF_TIME_LOW = 2
    DONT_TEST = 1


class TestrailCaseType(object):
    """
    Testrail Priority class
    """

    ADMINISTRATION = 'Administration'
    AT_EXT = 'AT_Extensive'
    AT_QUICK = 'AT_Quick'
    FUNCTIONAL = 'Functionality'
    MANUAL = 'Manual'
    PERFORMANCE = 'Performance'
    REGRESSION = 'Regression'
    STABILITY = 'Stability'


class TestrailApi(object):
    """
    Testrail API class
        - on init will load all existing projects
        - projects / suites / sections are not mutable via this class so are assumed to be present
          this allows more control on testrail
        - testcases can be added dynamically to an already existing project/suite/(sub)section combo
    """

    def __init__(self, server, user=None, password=None, key=None):
        self.server = server
        assert (user and password) or key, \
            "Credentials are needed for testrail connection, specify either user/password or basic auth key"
        self.base64_authentication = key or base64.encodestring('%s:%s' % (user, password)).replace('\n', '')
        self.URL = "http://%s/index.php?/api/v2/%s"
        self.projects = self.get_projects()
        self.AT_QUICK_ID = self.get_case_type_by_name('AT_Quick')['id']

    def _get_from_testrail(self, testrail_item, main_id=None, url_params=None):
        if main_id:
            url = self.URL % (self.server, '%s/%s' % (testrail_item, main_id))
            if url_params:
                for key in url_params:
                    url += "&%s=%s" % (key, url_params[key])
        else:
            url = self.URL % (self.server, testrail_item)

        headers = {'Content-Type': 'application/json', 'Authorization': "Basic %s" % self.base64_authentication}

        try:
            content = requests.get(url, headers=headers)
        except urllib2.HTTPError as e:
            print e.reason
            raise
        except urllib2.URLError as e:
            print e
            print e.reason
            raise
        except:
            raise

        return content.json()

    def _add_to_testrail(self, testrail_item, main_id=None, values=None, sub_id=None):

        if main_id:
            main_id = str(main_id)
            if sub_id:
                url = self.URL % (self.server, '%s/%s/%s' % (testrail_item, main_id, sub_id))
            else:
                url = self.URL % (self.server, '%s/%s' % (testrail_item, main_id))
        else:
            url = self.URL % (self.server, '%s' % testrail_item)

        headers = {'Content-Type': 'application/json', 'Authorization': "Basic %s" % self.base64_authentication}

        try:
            content = requests.post(url, json=values, headers=headers)
        except urllib2.HTTPError as e:
            print e.reason
            raise
        except urllib2.URLError as e:
            print e.reason
            raise
        except:
            raise

        return content.json() if content.json() else None

    def get_case(self, case_id):
        return self._get_from_testrail("get_case", case_id)

    def get_cases(self, project_id, suite_id, section_id=None):
        extra_params = {'suite_id': suite_id}
        if section_id:
            extra_params['section_id'] = section_id
        return self._get_from_testrail("get_cases", project_id, extra_params)

    def add_case(self, section_id, title, type_id=None, priority_id=None, estimate=None, milestone_id=None, refs=None,
                 custom_fields=None):
        extra_params = {'title': title}
        if not type_id:
            type_id = self.AT_QUICK_ID
        extra_params['type_id'] = type_id
        if priority_id:
            extra_params['priority_id'] = priority_id
        if estimate:
            extra_params['estimate'] = estimate
        if milestone_id:
            extra_params['milestone_id'] = milestone_id
        if refs:
            extra_params['refs'] = refs
        if custom_fields:
            for key, value in custom_fields.iteritems():
                assert "custom_" in key, "Custom fields need to start with 'custom_'"
                extra_params[key] = value
        return self._add_to_testrail('add_case', section_id, extra_params)

    def update_case(self, case_id, title=None, type_id=None, priority_id=None, estimate=None, milestone_id=None,
                    refs=None, custom_fields=None):
        extra_params = {}
        if title:
            extra_params['title'] = title
        if type_id:
            extra_params['type_id'] = type_id
        if priority_id:
            extra_params['priority_id'] = priority_id
        if estimate:
            extra_params['estimate'] = estimate
        if milestone_id:
            extra_params['milestone_id'] = milestone_id
        if refs:
            extra_params['refs'] = refs
        if custom_fields:
            for key, value in custom_fields.iteritems():
                assert "custom_" in key, "Custom fields need to start with 'custom_'"
                extra_params[key] = value
        return self._add_to_testrail('update_case', case_id, extra_params)

    def delete_case(self, case_id):
        return self._add_to_testrail('delete_case', case_id)

    def get_case_fields(self):
        return self._get_from_testrail("get_case_fields")

    def get_case_types(self):
        return self._get_from_testrail("get_case_types")

    def get_case_type_by_name(self, name):
        case_types = [case_type for case_type in self.get_case_types() if case_type['name'] == name]
        if not case_types or len(case_types) > 1:
            raise Exception("No or multiple case types found with name: {0} ".format(name))
        return case_types[0]

    def get_section(self, section_id):
        return self._get_from_testrail("get_section", section_id)

    def get_sections(self, project_id, suite_id):
        return self._get_from_testrail("get_sections", project_id, {'suite_id': suite_id})

    def get_section_by_name(self, project_id, suite_id, name):
        sections = [section for section in self.get_sections(project_id, suite_id) if section['name'] == name]
        if not sections or len(sections) > 1:
            raise Exception("No or multiple suites found with name: {0} ".format(name))
        return sections[0]

    def get_suite(self, suite_id):
        return self._get_from_testrail('get_suite', suite_id)

    def get_suites(self, project_id):
        return self._get_from_testrail('get_suites', project_id)

    def get_suite_by_name(self, project_id, name):
        suites = [suite for suite in self.get_suites(project_id) if suite['name'] == name]
        if not suites or len(suites) > 1:
            raise Exception("No or multiple suites found with name: {0} ".format(name))
        return suites[0]

    def get_plan(self, plan_id):
        return self._get_from_testrail('get_plan', plan_id)

    def get_plans(self, project_id):
        return self._get_from_testrail('get_plans', project_id)

    def add_plan(self, project_id, name, description=None, milestone_id=None, entries=None):
        extra_params = {'name': name}
        if description:
            extra_params['description'] = description
        if milestone_id:
            extra_params['milestone_id'] = milestone_id
        if entries:
            extra_params['entries'] = entries
        return self._add_to_testrail('add_plan', project_id, extra_params)

    def add_plan_entry(self, plan_id, suite_id, name, assigned_to_id=None, include_all=True, case_ids=None):
        extra_params = {'suite_id': suite_id, 'name': name}
        if assigned_to_id:
            extra_params['assignedto_id'] = assigned_to_id
        if not include_all and case_ids:
            extra_params['include_all'] = False
            extra_params['case_ids'] = case_ids

        return self._add_to_testrail('add_plan_entry', plan_id, extra_params)

    def update_plan(self, plan_id, name, description=None, milestone_id=None):
        extra_params = {'name': name}
        if description:
            extra_params['description'] = description
        if milestone_id:
            extra_params['milestone_id'] = milestone_id
        return self._add_to_testrail('update_plan', plan_id, extra_params)

    def update_plan_entry(self, plan_id, entry_id, include_all=True, case_ids=None):
        extra_params = dict()
        if not include_all and case_ids:
            extra_params['include_all'] = False
            extra_params['case_ids'] = case_ids

        return self._add_to_testrail('update_plan_entry', plan_id, extra_params, entry_id)

    def close_plan(self, plan_id):
        return self._add_to_testrail('close_plan', plan_id)

    def delete_plan(self, plan_id):
        return self._add_to_testrail('delete_plan', plan_id)

    def get_priorities(self):
        return self._get_from_testrail("get_priorities")

    def get_project(self, project_id):
        return self._get_from_testrail('get_project', project_id)

    def get_projects(self):
        return self._get_from_testrail("get_projects")

    def get_project_by_name(self, name):
        projects = [project for project in self.projects if project['name'] == name]
        if not projects or len(projects) > 1:
            raise Exception("No or multiple projects found with name: {0} ".format(name))
        return projects[0]

    def get_result_fields(self):
        return self._get_from_testrail("get_result_fields")

    def get_run(self, run_id):
        return self._get_from_testrail('get_run', run_id)

    def get_runs(self, project_id):
        return self._get_from_testrail('get_runs', project_id)

    def add_run(self, project_id, suite_id, name, description=None, assigned_to_id=None, include_all=True,
                case_ids=None):
        extra_params = {'suite_id': suite_id, 'name': name}
        if description:
            extra_params['description'] = description
        if assigned_to_id:
            extra_params['assignedto_id'] = assigned_to_id
        if not include_all and case_ids:
            extra_params['include_all'] = False
            extra_params['case_ids'] = case_ids
        return self._add_to_testrail('add_run', project_id, extra_params)

    def update_run(self, run_id, name, description=None, include_all=True, case_ids=None):
        extra_params = {'name': name}
        if description:
            extra_params['description'] = description
        if not include_all and case_ids:
            extra_params['include_all'] = False
            extra_params['case_ids'] = case_ids
        return self._add_to_testrail('update_run', run_id, extra_params)

    def close_run(self, run_id):
        return self._add_to_testrail('close_run', run_id)

    def delete_run(self, run_id):
        return self._add_to_testrail('delete_run', run_id)

    def get_test(self, test_id):
        return self._get_from_testrail('get_test', test_id)

    def get_tests(self, run_id):
        return self._get_from_testrail('get_tests', run_id)

    def get_results(self, test_id, limit=None):
        extra_params = {'limit': limit} if limit else None
        return self._get_from_testrail('get_results', test_id, extra_params)

    def add_result(self, test_id, status_id, comment=None, version=None, elapsed=None, defects=None,
                   assigned_to_id=None, custom_fields=None):
        extra_params = {'status_id': status_id}
        if comment:
            extra_params['comment'] = comment
        if version:
            extra_params['version'] = version
        if elapsed:
            extra_params['elapsed'] = elapsed
        if defects:
            extra_params['defects'] = defects
        if assigned_to_id:
            extra_params['assignedto_id'] = assigned_to_id
        if custom_fields:
            for key, value in custom_fields.iteritems():
                assert "custom_" in key, "Custom fields need to start with 'custom_'"
                extra_params[key] = value
        return self._add_to_testrail('add_result', test_id, extra_params)

    def add_result_for_case(self, run_id, case_id, status_id, comment=None, version=None, elapsed=None, defects=None,
                            assigned_to_id=None, custom_fields=None):
        extra_params = {'status_id': status_id}
        if comment:
            extra_params['comment'] = comment
        if version:
            extra_params['version'] = version
        if elapsed:
            extra_params['elapsed'] = elapsed
        if defects:
            extra_params['defects'] = defects
        if assigned_to_id:
            extra_params['assignedto_id'] = assigned_to_id
        if custom_fields:
            for key, value in custom_fields.iteritems():
                assert "custom_" in key, "Custom fields need to start with 'custom_'"
                extra_params[key] = value
        return self._add_to_testrail('add_result_for_case', "%s/%s" % (run_id, case_id), extra_params)

    def get_statuses(self):
        return self._get_from_testrail('get_statuses')

    def get_milestone(self, milestone_id):
        return self._get_from_testrail('get_milestone', milestone_id)

    def get_milestones(self, project_id):
        return self._get_from_testrail('get_milestones', project_id)

    def get_milestone_by_name(self, project_id, name):
        milestones = [milestone for milestone in self.get_milestones(project_id) if milestone['name'] == name]
        if not milestones or len(milestones) > 1:
            raise Exception("No or multiple suites found with name: {0} ".format(name))
        return milestones[0]

    def get_case_by_name(self, project_id, suite_id, name, section_id=None):
        cases = [case for case in self.get_cases(project_id, suite_id, section_id) if case['title'] == name]
        if not cases or len(cases) > 1:
            raise Exception("No or multiple cases found with name: {0} ".format(name))
        return cases[0]

    def get_test_by_name(self, run_id, name):
        tests = [test for test in self.get_tests(run_id) if test['title'] == name]
        if not tests or len(tests) > 1:
            raise Exception("No or multiple tests found with name: {0} ".format(name))
        return tests[0]

