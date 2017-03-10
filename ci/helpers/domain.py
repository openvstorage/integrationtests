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

from ovs.dal.lists.domainlist import DomainList
from ovs.dal.lists.storagedriverlist import StorageDriverList


class DomainHelper(object):
    """
    DomainHelper class
    """

    def __init__(self):
        pass

    @staticmethod
    def get_domainguid_by_name(domain_name):
        """
        Fetch domain guid by name

        :param domain_name: ip address of a storagerouter
        :type domain_name: str
        :return: domain guid
        :rtype: str
        """

        return DomainHelper.get_domain_by_name(domain_name).guid

    @staticmethod
    def get_domain_by_name(domain_name):
        """
        Fetch domain by name

        :param domain_name: correctly spelled name of a domain
        :type domain_name: str
        :return: domain object
        :rtype: ovs.dal.hybrids.domain.Domain
        """

        for domain in DomainList.get_domains():
            if domain.name == domain_name:
                return domain

    @staticmethod
    def get_domain_by_guid(domain_guid):
        """
        Fetch disk partitions by disk guid

        :param domain_guid: guid of a domain
        :type domain_guid: str
        :return: domain object
        :rtype: ovs.dal.hybrids.domain.Domain
        """

        for domain in DomainList.get_domains():
            if domain.guid == domain_guid:
                return domain

    @staticmethod
    def get_domain_guids():
        """
        Fetch domain guids

        :return: list of strings
        :rtype: list
        """

        return [domain.guid for domain in DomainList.get_domains()]

    @staticmethod
    def get_domains():
        """
        Fetch domains

        :return: list with ovs.dal.hybrids.domain.Domain objects
        :rtype: list
        """

        return DomainList.get_domains()

    @staticmethod
    def get_storagerouters_in_same_domain(domain_guid):
        """
        Get storagerouter guids in a domain

        :param domain_guid: guid of a domain
        :type domain_guid: str
        :return: list of storagerouter guids
        :rtype: list
        """

        return DomainHelper.get_domain_by_guid(domain_guid=domain_guid)['storage_router_layout']['regular']

    @staticmethod
    def get_storagedrivers_in_same_domain(domain_guid):
        """
        Get storagerouter guids in a domain

        :param domain_guid: guid of a domain
        :type domain_guid: str
        :return: list of storagerouter guids
        :rtype: list
        """

        return [storagedriver for storagedriver in StorageDriverList.get_storagedrivers()
                if domain_guid in storagedriver.storagerouter.regular_domains]
