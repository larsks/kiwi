import logging
import re
import subprocess

from exc import *

re_label = re.compile(r'''\d+: \s+ (?P<ifname>\S+) \s+ inet \s+
                      (?P<ipv4addr>\S+) \s+ scope \s+ (?P<scope>\S+) \s+
                      (?P<flags>.*)''', re.VERBOSE)

LOG = logging.getLogger(__name__)


class Interface (object):
    '''This is a network interface driver for Kiwi.  It is responsible for
    adding and removing address to and from network interfaces.'''

    def __init__(self,
                 interface='eth0',
                 label='kube'):
        self.interface = interface
        self.label = label

        self.remove_labelled_addresses()

    def remove_labelled_addresses(self):
        '''Remove all addresses labelled with self.label from
        self.interface.'''

        try:
            out = subprocess.check_output([
                'ip', '-o', 'addr', 'show',
                'label', '%s:%s' % (self.interface, self.label)
            ])
        except subprocess.CalledProcessError as exc:
            raise InterfaceDriverError(reason=exc)

        # we're parsing the output of the 'ip' command here, which always
        # makes me nervous.
        for line in out.splitlines():
            m = re_label.match(line)
            if not m:
                LOG.warn('unexpected interface configuration: %s',
                         line)
                continue

            address = m.group('ipv4addr').split('/')[0]
            self.remove_address(address)

    def add_address(self, address):
        '''Add the given address to the managed interface.'''
        LOG.info('add address %s to device %s',
                 address,
                 self.interface)
        try:
            # Note that we're using the 'label' option here to apply a
            # label to the address.  This allows us to identify addresses
            # that we have added, which in turns allows us to clean them up
            # at startup without needing to otherwise preserve state.
            subprocess.check_call([
                'ip', 'addr', 'add',
                '%s/32' % address,
                'label', '%s:%s' % (self.interface, self.label),
                'dev', self.interface
            ])
        except subprocess.CalledProcessError as exc:
            raise InterfaceDriverError(reason=exc)

    def remove_address(self, address):
        '''Remove the given address from the managed interface.'''
        LOG.info('remove address %s from device %s',
                 address,
                 self.interface)
        try:
            subprocess.check_call([
                'ip', 'addr', 'del',
                '%s/32' % address,
                'dev', self.interface
            ])
        except subprocess.CalledProcessError as exc:
            raise InterfaceDriverError(reason=exc)

    def cleanup(self):
        self.remove_labelled_addresses()
