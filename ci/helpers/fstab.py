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


class FstabHelper(file):
    """
    Class to help with Fstab manipulations
    Inherits from file class
    """
    import os

    class Entry(object):
        """
        Entry class represents a non-comment line on the `/etc/fstab` file
        """

        def __init__(self, device, mountpoint, filesystem, options, d=0, p=0):
            self.device = device
            self.mountpoint = mountpoint
            self.filesystem = filesystem

            if not options:
                options = "defaults"

            self.options = options
            self.d = d
            self.p = p

        def __eq__(self, o):
            return str(self) == str(o)

        def __str__(self):
            return "{} {} {} {} {} {}".format(self.device, self.mountpoint, self.filesystem, self.options, self.d, self.p)

    DEFAULT_PATH = os.path.join(os.path.sep, 'etc', 'fstab')

    def __init__(self, path=None):
        if path:
            self._path = path
        else:
            self._path = self.DEFAULT_PATH
        file.__init__(self, self._path, 'r+')

    @staticmethod
    def _hydrate_entry(line):
        """
        Parse and add a line from fstab
        :param line: line that is present in fstab
        :type line: str
        :return:
        """
        return FstabHelper.Entry(*filter(lambda x: x not in ('', None), line.strip("\n").split(" ")))

    @property
    def entries(self):
        """
        Property containing all non-comment entries
        :return:
        """
        self.seek(0)
        for line in self.readlines():
            try:
                if not line.startswith("#"):
                    yield self._hydrate_entry(line)
            except ValueError:
                pass

    def get_entry_by_attr(self, attr, value):
        """
        Returns an entry with where a attr has a specific value
        :param attr: attribute from the entry
        :param value: value that the attribute should have
        :return:
        """
        for entry in self.entries:
            e_attr = getattr(entry, attr)
            if e_attr == value:
                return entry
        return None

    def add_entry(self, entry):
        """
        Adds an entry in fstab
        :param entry: entry object to add to fstab
        :return:
        """
        if self.get_entry_by_attr('device', entry.device):
            return False

        self.write(str(entry) + '\n')
        self.truncate()
        return entry

    def remove_entry(self, entry):
        """
        Removes a line from fstab
        :param entry:entry object
        :return:
        """
        self.seek(0)

        lines = self.readlines()

        found = False
        for index, line in enumerate(lines):
            if not line.startswith("#"):
                if self._hydrate_entry(line) == entry:
                    found = True
                    break

        if not found:
            return False

        lines.remove(line)

        self.seek(0)
        self.write(''.join(lines))
        self.truncate()
        return True

    def remove_by_mountpoint(self, mountpoint):
        """
        Removes an entry by specific mountpoint
        :param mountpoint: mountpoint
        :return:
        """
        entry = self.get_entry_by_attr('mountpoint', mountpoint)
        if entry:
            return self.remove_entry(entry)
        return False

    def add(self, device, mountpoint, filesystem, options=None, dump=None, pass_=None):
        """
        Adds a entry based on supplied params
        :param device: devicename eg /dev/sda
        :param mountpoint: point where the device is mounted eg /mnt/sda
        :param filesystem: type of filesystem eg ext4
        :param options: extra options eg 'defaults'
        :param path:
        :return:
        """
        return self.add_entry(FstabHelper.Entry(device, mountpoint, filesystem, options, dump))
