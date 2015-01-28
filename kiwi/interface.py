import logging
import re
import subprocess

from exc import *

# 5: br0    inet 192.168.1.42/32 scope global br0:kube\       valid_lft forever preferred_lft forever

re_label = re.compile(r'''\d+: \s+ (?P<ifname>\S+) \s+ inet \s+
                      (?P<ipv4addr>\S+) \s+ scope \s+ (?P<scope>\S+) \s+
                      (?P<flags>.*)''', re.VERBOSE)

class Interface (object):

    log = logging.getLogger('kiwi.interface')

    def __init__(self,
                 interface='eth0',
                 label='kube'):
        self.interface = interface
        self.label = label

        self.remove_labelled_addresses()

    def remove_labelled_addresses(self):
        try:
            out = subprocess.check_output([
                'ip', '-o', 'addr', 'show',
                'label', '%s:%s' % (self.interface, self.label)
            ], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            raise InterfaceDriverError(status=exc)

        for line in out.splitlines():
            m = re_label.match(line)
            if not m:
                self.log.warn('unexpected interface configuration: %s',
                              line)
                continue

            address = m.group('ipv4addr').split('/')[0]
            self.remove_address(address)

    def add_address(self, address):
        self.log.info('add address %s to device %s',
                      address,
                      self.interface)
        try:
            subprocess.check_call([
                'ip', 'addr', 'add',
                '%s/32' % address,
                'label', '%s:%s' % (self.interface, self.label),
                'dev', self.interface
            ])
        except subprocess.CalledProcessError as exc:
            raise InterfaceDriverError(status=exc)

    def remove_address(self, address):
        self.log.info('remove address %s from device %s',
                      address,
                      self.interface)
        try:
            subprocess.check_call([
                'ip', 'addr', 'del',
                '%s/32' % address,
                'dev', self.interface
            ])
        except subprocess.CalledProcessError as exc:
            raise InterfaceDriverError(status=exc)

