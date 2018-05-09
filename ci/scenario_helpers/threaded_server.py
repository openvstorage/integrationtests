#  Copyright (C) 2016 iNuron NV
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

import time
import Queue
import socket
import threading
from ovs.extensions.generic.logger import Logger
from ovs_extensions.generic.remote import remote


class ThreadedServer(object):
    """
    Server class that can listen to a host:port combination for messages, and react correspondingly
    """
    logger = Logger('scenario_helpers-threaded_server')

    def __init__(self, host, port, message_queue=None, remote_ip=None):
        self.host = host
        self.port = port
        self.work_queue = Queue.Queue()
        self.work_queue.put('test')
        if remote_ip is not None:
            self.remote = remote(remote_ip, [socket])
            self._remote = self.remote.__enter__()
            self.sock = self._remote.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.remote = None
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(1)
        self.sock.bind((self.host, self.port))
        self.logger.debug('Bound to {0}:{1}'.format(*self.sock.getsockname()))
        self.listening_thread = None
        if message_queue is None:
            message_queue = Queue.Queue()
        self.message_queue = message_queue
        self.received_messages = []

    def get_listening_port(self):
        """
        Return the port the server is listening to
        :return: socket number
        """
        return self.sock.getsockname()[1]

    def __del__(self):
        # Destructor
        if self.remote is not None:
            self.remote.__exit__()

    def listen_threaded(self):
        """
        Initiate the threaded listening for messages
        :return: None
        """
        thread = threading.Thread(target=self._listen, args=())
        thread.start()
        self.listening_thread = thread

    def close_socket(self):
        """
        Close the listening socket
        :return: None
        """
        self.sock.close()  # Close before sending
        if self.remote is not None:
            self.remote.__exit__()

    def _listen(self):
        try:
            self.sock.listen(5)
            while True:
                try:
                    conn, address = self.sock.accept()
                    conn.settimeout(60)
                    threading.Thread(target=self._listen_to_client, args=(conn, address)).start()
                except socket.timeout:
                    pass
        except Exception:
            self.logger.exception('Unhandled exception during listening')
        finally:
            self.sock.close()

    def _listen_to_client(self, client, address):
        _ = address
        size = 1024
        try:
            while True:
                try:
                    data = client.recv(size)
                    if data:
                        self.received_messages.append({'address': address, 'data': data})
                        self.logger.debug('Connector ({0}:{1}) said: {2}'.format(address[0], address[1], data))
                    else:
                        raise socket.error('Client disconnected')
                except Exception:
                    return False
        finally:
            client.close()

    def wait_for_messages(self, messages=None, timeout=None):
        """
        The listening thread should already be started outside of this function
        Listen untill all given items have been mentioned by our sockets listener
        :param messages: Messages to wait for. This function will wait until all the given messages have been received
        :type messages: list
        :param timeout: Timeout in seconds
        :type timeout: int
        :return: vm ip info
        :rtype: dict
        """
        if messages is None:
            messages = []
        messages = messages[:]  # Shallow copy as we are popping an element from the list
        start = time.time()
        vm_ips_info = {}
        try:
            self.logger.debug('Messages to wait for: {0}'.format(messages))
            while len(messages) > 0:  # and not stop_event.is_set()
                if timeout is not None and time.time() - start > timeout:
                    raise RuntimeError('Listening timed out after {0} minutes'.format(str(int(timeout/60))))
                for received_message_info in self.received_messages:
                    address = received_message_info['address']
                    data = received_message_info['data']
                    self.logger.debug('Checking if received message (\'{0}\') was included in the messages'.format(data))
                    if data in messages:
                        self.logger.debug('Received message (\'{0}\') was included in the messages'.format(data))
                        messages.remove(data)
                        vm_name = data.rsplit('_', 1)[-1]
                        self.logger.debug('Recognized sender as {0}'.format(vm_name))
                        vm_ips_info[vm_name] = {'ip': address[0]}
                time.sleep(0.5)
        finally:  # Always close our socket
            self.close_socket()  # Force the thread to halt
            if self.listening_thread is not None:
                self.listening_thread.join()
        return vm_ips_info
