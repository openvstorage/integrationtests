# Copyright 2014 Open vStorage NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import base64
import urllib2


class TestrailApi:
    def __init__(self, testrailIp, user=None, password=None, key=None):
        self.testrailIp = testrailIp
        assert (
                   user and password) or key, "Credentials are needed for testrail connection, specify either user/password or basic auth key"
        self.base64userpass = key or base64.encodestring('%s:%s' % (user, password)).replace('\n', '')
        self.URL = "http://%s/index.php?/api/v2/%s"

    def _getFromTestRail(self, testrailItem, mainId=None, urlParams=None):
        if mainId:
            url = self.URL % (self.testrailIp, '%s/%s' % (testrailItem, mainId))
            if urlParams:
                for key in urlParams:
                    url += "&%s=%s" % (key, urlParams[key])
        else:
            url = self.URL % (self.testrailIp, testrailItem)
        request = urllib2.Request(url, headers={'Content-Type': 'application/json'})
        request.add_header("Authorization", "Basic %s" % self.base64userpass)

        try:
            content = urllib2.urlopen(request).readline()
        except urllib2.HTTPError as e:
            print e.readlines()
            raise
        except urllib2.URLError as e:
            print e
            print e.readlines()
            raise
        except:
            raise

        result = json.loads(content)
        return result

    def _addToTestRail(self, testrailItem, mainId=None, values=None):

        if mainId:
            mainId = str(mainId)
            url = self.URL % (self.testrailIp, '%s/%s' % (testrailItem, mainId))
        else:
            url = self.URL % (self.testrailIp, '%s' % (testrailItem))
        data = json.dumps(values)

        req = urllib2.Request(url, headers={'Content-Type': 'application/json'})
        req.add_header("Authorization", "Basic %s" % self.base64userpass)

        try:
            response = urllib2.urlopen(req, data)
        except urllib2.HTTPError as e:
            print e.readlines()
            raise
        except urllib2.URLError as e:
            print e.readlines()
            raise
        except:
            raise

        content = response.read()
        result = json.loads(content) if content else None
        return result

    def getCase(self, caseId):
        return self._getFromTestRail("get_case", caseId)

    def getCases(self, projectId, suiteId, sectionId=None):
        extraParams = {'suite_id': suiteId}
        if sectionId:
            extraParams['section_id'] = sectionId
        return self._getFromTestRail("get_cases", projectId, extraParams)

    def addCase(self, sectionId, title, typeId=None, priorityId=None, estimate=None, milestoneId=None, refs=None,
                customFields=None):
        extraParams = {'title': title}
        if typeId:
            extraParams['type_id'] = typeId
        if priorityId:
            extraParams['priority_id'] = priorityId
        if estimate:
            extraParams['estimate'] = estimate
        if milestoneId:
            extraParams['milestone_id'] = milestoneId
        if refs:
            extraParams['refs'] = refs
        if customFields:
            for k, v in customFields.iteritems():
                assert "custom_" in k, "Custom fields need to start with 'custom_'"
                extraParams[k] = v
        return self._addToTestRail('add_case', sectionId, extraParams)

    def updateCase(self, caseId, title=None, typeId=None, priorityId=None, estimate=None, milestoneId=None, refs=None,
                   customFields=None):
        extraParams = {}
        if title:
            extraParams['title'] = title
        if typeId:
            extraParams['type_id'] = typeId
        if priorityId:
            extraParams['priority_id'] = priorityId
        if estimate:
            extraParams['estimate'] = estimate
        if milestoneId:
            extraParams['milestone_id'] = milestoneId
        if refs:
            extraParams['refs'] = refs
        if customFields:
            for k, v in customFields.iteritems():
                assert "custom_" in k, "Custom fields need to start with 'custom_'"
                extraParams[k] = v
        return self._addToTestRail('update_case', caseId, extraParams)

    def deleteCase(self, caseId):
        return self._addToTestRail('delete_case', caseId)

    def getCaseFields(self):
        return self._getFromTestRail("get_case_fields")

    def getCaseTypes(self):
        return self._getFromTestRail("get_case_types")

    def getSection(self, sectionId):
        return self._getFromTestRail("get_section", sectionId)

    def getSections(self, projectId, suiteId):
        return self._getFromTestRail("get_sections", projectId, {'suite_id': suiteId})

    def addSection(self, projectId, suiteId, name, parentId=None):
        extraParams = {'suite_id': suiteId,
                       'name': name}
        if parentId:
            extraParams['parent_id'] = parentId
        return self._addToTestRail('add_section', projectId, extraParams)

    def updateSection(self, sectionId, name):
        return self._addToTestRail('update_section', sectionId, {'name': name})

    def deleteSection(self, sectionId):
        return self._addToTestRail('delete_section', sectionId)

    def getSuite(self, suiteId):
        return self._getFromTestRail('get_suite', suiteId)

    def getSuites(self, projectId):
        return self._getFromTestRail('get_suites', projectId)

    def addSuite(self, projectId, suiteName, suiteDescription=''):
        extraParams = {'name': suiteName}
        if suiteDescription:
            extraParams['description'] = suiteDescription
        return self._addToTestRail('add_suite', projectId, extraParams)

    def updateSuite(self, suiteId, suiteName, suiteDescription=''):
        extraParams = {'name': suiteName}
        if suiteDescription:
            extraParams['description'] = suiteDescription
        return self._addToTestRail('update_suite', suiteId, extraParams)

    def deleteSuite(self, suiteId):
        return self._addToTestRail('delete_suite', suiteId)

    def getPlan(self, planId):
        return self._getFromTestRail('get_plan', planId)

    def getPlans(self, projectId):
        return self._getFromTestRail('get_plans', projectId)

    def addPlan(self, projectId, name, description=None, milestoneId=None, entries=None):
        extraParams = {'name': name}
        if description:
            extraParams['description'] = description
        if milestoneId:
            extraParams['milestone_id'] = milestoneId
        if entries:
            extraParams['entries'] = entries
        return self._addToTestRail('add_plan', projectId, extraParams)

    def addPlanEntry(self, planId, suiteId, name, assignedtoId=None, includeAll=True, caseIds=None):
        extraParams = {'suite_id': suiteId,
                       'name': name}
        if assignedtoId:
            extraParams['assignedto_id'] = assignedtoId
        if not includeAll and caseIds:
            extraParams['include_all'] = False
            extraParams['case_ids'] = caseIds

        return self._addToTestRail('add_plan_entry', planId, extraParams)

    def updatePlan(self, planId, name, description=None, milestoneId=None):
        extraParams = {'name': name}
        if description:
            extraParams['description'] = description
        if milestoneId:
            extraParams['milestone_id'] = milestoneId
        return self._addToTestRail('update_plan', planId, extraParams)

    def closePlan(self, planId):
        return self._addToTestRail('close_plan', planId)

    def deletePlan(self, planId):
        return self._addToTestRail('delete_plan', planId)

    def getPriorities(self):
        return self._getFromTestRail("get_priorities")

    def getProject(self, projectId):
        return self._getFromTestRail('get_project', projectId)

    def getProjects(self):
        return self._getFromTestRail("get_projects")

    def addProject(self, name, announcement=None, showAnnouncement=None):
        extraParams = {'name': name}
        if announcement:
            extraParams['announcement'] = announcement
        if showAnnouncement:
            extraParams['show_announcement'] = showAnnouncement
        return self._addToTestRail('add_project', values=extraParams)

    def updateProject(self, projectId, isCompleted):
        extraParams = {'is_completed': isCompleted}
        return self._addToTestRail('update_project', projectId, values=extraParams)

    def getResultFields(self):
        return self._getFromTestRail("get_result_fields")

    def getRun(self, runId):
        return self._getFromTestRail('get_run', runId)

    def getRuns(self, projectId):
        return self._getFromTestRail('get_runs', projectId)

    def addRun(self, projectId, suiteId, name, description=None, assignedtoId=None, includeAll=True, caseIds=None):
        extraParams = {'suite_id': suiteId,
                       'name': name}
        if description:
            extraParams['description'] = description
        if assignedtoId:
            extraParams['assignedto_id'] = assignedtoId
        if not includeAll and caseIds:
            extraParams['include_all'] = False
            extraParams['case_ids'] = caseIds
        return self._addToTestRail('add_run', projectId, extraParams)

    def updateRun(self, runId, name, description=None, includeAll=True, caseIds=None):
        extraParams = {'name': name}
        if description:
            extraParams['description'] = description
        if not includeAll and caseIds:
            extraParams['include_all'] = False
            extraParams['case_ids'] = caseIds
        return self._addToTestRail('update_run', runId, extraParams)

    def closeRun(self, runId):
        return self._addToTestRail('close_run', runId)

    def deleteRun(self, runId):
        return self._addToTestRail('delete_run', runId)

    def getTest(self, testId):
        return self._getFromTestRail('get_test', testId)

    def getTests(self, runId):
        return self._getFromTestRail('get_tests', runId)

    def getResults(self, testId, limit=None):
        extraParams = {'limit': limit} if limit else None
        return self._getFromTestRail('get_results', testId, extraParams)

    def addResult(self, testId, statusId, comment=None, version=None, elapsed=None, defects=None, assignedtoId=None,
                  customFields=None):
        extraParams = {'status_id': statusId}
        if comment:
            extraParams['comment'] = comment
        if version:
            extraParams['version'] = version
        if elapsed:
            extraParams['elapsed'] = elapsed
        if defects:
            extraParams['defects'] = defects
        if assignedtoId:
            extraParams['assignedto_id'] = assignedtoId
        if customFields:
            for k, v in customFields.iteritems():
                assert "custom_" in k, "Custom fields need to start with 'custom_'"
                extraParams[k] = v
        return self._addToTestRail('add_result', testId, extraParams)

    def addResultForCase(self, runId, caseId, statusId, comment=None, version=None, elapsed=None, defects=None,
                         assignedtoId=None, customFields=None):
        extraParams = {'status_id': statusId}
        if comment:
            extraParams['comment'] = comment
        if version:
            extraParams['version'] = version
        if elapsed:
            extraParams['elapsed'] = elapsed
        if defects:
            extraParams['defects'] = defects
        if assignedtoId:
            extraParams['assignedto_id'] = assignedtoId
        if customFields:
            for k, v in customFields.iteritems():
                assert "custom_" in k, "Custom fields need to start with 'custom_'"
                extraParams[k] = v
        return self._addToTestRail('add_result_for_case', "%s/%s" % (runId, caseId), extraParams)

    def getStatuses(self):
        return self._getFromTestRail('get_statuses')

    def getMilestone(self, milestoneId):
        return self._getFromTestRail('get_milestone', milestoneId)

    def getMilestones(self, projectId):
        return self._getFromTestRail('get_milestones', projectId)

    def addMilestone(self, projectId, name, description=None, dueOn=None):
        extraParams = {'name': name}
        if description:
            extraParams['description'] = description
        if dueOn:
            extraParams['due_on'] = dueOn
        return self._addToTestRail('add_milestone', projectId, extraParams)

    def updateMilestone(self, milestoneId, isCompleted):
        return self._addToTestRail('update_milestone', milestoneId, {'is_completed': isCompleted})

    def deleteMilestone(self, milestoneId):
        return self._addToTestRail('delete_milestone', milestoneId)
