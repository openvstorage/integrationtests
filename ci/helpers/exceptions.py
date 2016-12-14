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
Exceptions module
"""


class SectionNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class AlbaNodeNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class DirectoryNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class ArakoonClusterNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class UnsupportedInitManager(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class PresetNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class AlbaBackendNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class VPoolNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class VDiskNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class VPoolNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class ImageConvertError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass
