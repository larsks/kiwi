import logging
import subprocess

import defaults
import iptables
from exc import *


LOG = logging.getLogger(__name__)


class Firewall (object):
    '''This is a firewall driver for kiwi, the Kubernetes address manager.
    This driver operates by creating rules in the `mangle` table that will
    apply a specific firewall mark to inbound packets.  The driver uses the
    mangle table in order to match packets before they are modified by the
    REDIRECT rules generated in the nat table by kube-proxy.'''

    def __init__(self,
                 fwchain=defaults.fwchain,
                 fwmark=defaults.fwmark):

        self.fwchain = fwchain
        self.fwmark = fwmark
        self.rules = set()

        self.create_chain()
        self.flush_rules()

    def cleanup(self):
        self.flush_rules()

    def create_chain(self):
        '''Create self.fwchain if it does not already exist.'''

        if iptables.mangle.chain_exists(self.fwchain):
            return

        LOG.info('creating chain %s', self.fwchain)
        try:
            iptables.mangle.create_chain(self.fwchain)
        except iptables.CommandError as exc:
            raise FirewallDriverError(reason=exc)

    def flush_rules(self):
        '''Flush all rules in self.fwchain.'''

        LOG.info('flushing all rules from %s',
                 self.fwchain)
        self.rules = set()
        try:
            iptables.mangle.flush_chain(self.fwchain)
        except iptables.CommandError as exc:
            raise FirewallDriverError(reason=exc)

    def rule_for(self, address, service):
        '''Generate an iptables rule (returned as a tuple) for the given
        address and service.'''

        return iptables.Rule(str(arg) for arg in [
            '-d', address,
            '-p', service['protocol'].lower(),
            '--dport', service['port'],
            '-m', 'comment',
            '--comment', service['id'],
            '-j', 'MARK', '--set-mark', self.fwmark
        ])

    def add_service(self, address, service):
        '''Add a new service to the firewall.'''

        rule = self.rule_for(address, service)
        if rule in self.rules:
            LOG.info('not adding rule for service %s '
                     'on %s port %d (already exists)',
                     service['id'], address, service['port'])
            return

        LOG.info('adding firewall rules for service %s '
                 'on %s port %d',
                 service['id'], address, service['port'])

        try:
            iptables.mangle.chains[self.fwchain].append(rule)
        except iptables.CommandError as exc:
            raise FirewallDriverError(reason=exc)
        else:
            self.rules.add(rule)

    def remove_service(self, address, service):
        '''Remove a service from the firewall.'''

        rule = self.rule_for(address, service)

        LOG.info('removing firewall rules for service %s '
                 'on %s port %d',
                 service['id'], address, service['port'])
        self.rules.remove(rule)
        try:
            iptables.mangle.chains[self.fwchain].remove(rule=rule)
        except iptables.CommandError as exc:
            raise FirewallDriverError(reason=exc)
