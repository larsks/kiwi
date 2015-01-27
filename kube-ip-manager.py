#!/usr/bin/python

'''Manages the assigned of public ips to interfaces and the associated
firewall rules for Kubernetes services.'''

import argparse
import json
import logging
import netaddr
import os
import requests
import subprocess
import sys
import time

from itertools import izip

# {
#     "object": {
#         "apiVersion": "v1beta1",
#         "containerPort": 9090,
#         "creationTimestamp": "2015-01-23T16:45:38-05:00",
#         "id": "squeezebox-cli",
#         "kind": "Service",
#         "namespace": "default",
#         "port": 9090,
#         "portalIP": "10.254.28.96",
#         "protocol": "TCP",
#         "publicIPs": [
#             "192.168.1.40"
#         ],
#         "resourceVersion": 119,
#         "selector": {
#             "name": "squeezebox"
#         },
#         "selfLink": "/api/v1beta1/services/squeezebox-cli",
#         "uid": "2b328eb1-a349-11e4-8c74-20cf30467e62"
#     },
#     "type": "ADDED"
# }


class CalledProcessError(Exception):
    def __init__(self, cmd=None, returncode=None,
                 stdout=None, stderr=None):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

        super(CalledProcessError, self).__init__(
            '%s failed with error: %s' % (cmd[0], stderr))


def run(*cmd):
    '''Run a command.  Raises CalledProcessError if the command exits
    with returncode != 0.  The CalledProcessError object will have the
    returncode, stdout, and stderr from the command.'''

    logging.debug('running: %s', ' '.join(cmd))

    if args.dry_run:
        return

    p = subprocess.Popen(cmd,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate()

    if p.returncode != 0:
        raise CalledProcessError(cmd=cmd,
                                 returncode=p.returncode,
                                 stdout=out,
                                 stderr=err)


class IPManager (object):
    '''A class for managing ip address assignment and firewall rules for
    Kubernetes services with publicIPs.'''

    log = logging.getLogger('ipmanager')

    def __init__(self,
                 interface='eth0',
                 fwchain='KUBE-PUBLIC',
                 fwmark='1',
                 cidrs=None):
        self.interface = interface
        self.fwchain = fwchain
        self.fwmark = fwmark
        self.cidrs = cidrs

        self.services = {}
        self.fwrules = {}
        self.addresses = {}

        self.init_firewall()

    def init_firewall(self):
        '''Make sure the firewall chain we will be managing both exists and
        is empty.'''

        try:
            run('iptables', '-t', 'mangle', '-S',
                self.fwchain)
        except CalledProcessError as err:
            if 'No chain/target/match by that name.' not in err.stderr:
                raise

            run('iptables', '-t', 'mangle',
                '-N', 'KUBE-PUBLIC')
        else:
            run('iptables', '-t', 'mangle', '-F',
                self.fwchain)

    def should_handle_address(self, ip):
        '''Check if the given address is contained by any of the address
        ranges we manage.'''

        if self.cidrs is None:
            return True

        for cidr in self.cidrs:
            cidr = netaddr.IPNetwork(cidr)
            if ip in cidr:
                return True

        return False

    def add_service(self, service):
        if 'publicIPs' not in service:
            self.log.warn('ignoring add for service %s with no public ips',
                          service['id'])
            return

        if service['id'] in self.services:
            self.log.warn('ignoring add for existing service %s',
                          service['id'])
            return

        self.log.info('adding service %s on port %s',
                      service['id'],
                      service['port'])

        self.services[service['id']] = service

        for ip in service['publicIPs']:
            if not self.should_handle_address(ip):
                self.log.warn('ignoring invalid address: %s', ip)
                continue

            if ip in self.addresses:
                self.addresses[ip] += 1
            else:
                self.addresses[ip] = 1
                self.add_ip_address(ip)

            self.add_fw_rule(service, ip)

    def add_fw_rule(self, service, ip):
        fwrule = ('-d', ip,
                  '-p', service['protocol'].lower(),
                  '--dport', '%s' % service['port'],
                  '-j', 'MARK',
                  '--set-mark', self.fwmark,
                  '-m', 'comment',
                  '--comment', service['id'])

        self.fwrules[service['id']] = fwrule

        self.log.info('adding fw rule: %s',
                      ' '.join(fwrule))
        run('iptables', '-t', 'mangle',
            '-A', self.fwchain, *fwrule)

    def remove_fw_rule(self, service, ip):
        fwrule = self.fwrules[service['id']]
        self.log.info('removing fw rule: %s',
                      ' '.join(fwrule))
        run('iptables', '-t', 'mangle',
            '-D', self.fwchain, *fwrule)

    def remove_service(self, service):
        if 'publicIPs' not in service:
            self.log.warn('ignoring remove for service %s with no public ips',
                          service['id'])
            return

        if service['id'] not in self.services:
            self.log.warn('ignoring remove for unknown service %s',
                          service['id'])
            return

        self.log.info('removing service %s on port %s',
                      service['id'],
                      service['port'])

        del self.services[service['id']]

        for ip in service['publicIPs']:
            if ip in self.addresses:
                self.addresses[ip] -= 1
                if self.addresses[ip] == 0:
                    self.remove_ip_address(ip)
                    del self.addresses[ip]

            self.remove_fw_rule(service, ip)

    def add_ip_address(self, ip):
        '''Adds an ip address to a network interface. These
        addresses are labelled with the `:kube` suffix so that they can
        easily be identified:

        ip addr show label *:kube'''

        self.log.info('adding address %s to interface %s',
                      ip, self.interface)
        try:
            run('ip', 'addr', 'add',
                '%s/32' % ip,
                'dev', self.interface,
                'label', '%s:kube' % self.interface)
        except CalledProcessError as err:
            if 'File exists' not in err.stderr:
                raise

    def remove_ip_address(self, ip):
        '''Remove an address from a network interface.'''
        self.log.info('removing address %s from interface %s',
                      ip, self.interface)
        try:
            run('ip', 'addr', 'del',
                '%s/32' % ip, 'dev', self.interface)
        except CalledProcessError as err:
            if 'Cannot assign requested address' not in err.stderr:
                raise

    def remove_all(self):
        '''Removes all services that we are managing (meant to be called on
        program exit)'''
        for service in self.services.values():
            self.remove_service(service)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--api-version', '-v',
                   default='v1beta1',
                   help='The API version to use when talking to the server')
    p.add_argument('--server', '-s',
                   default='http://localhost:8080',
                   help='The address of the Kubernetes API server')
    p.add_argument('--interface', '-i',
                   default='eth0',
                   help='Attach public ips to this interface')
    p.add_argument('--firewall-chain', '-f',
                   default='KUBE-PUBLIC',
                   help='Chain to manage in iptables mangle table')
    p.add_argument('--firewall-mark', '-m',
                   default='1',
                   help='fwmark applied in generated rules')
    p.add_argument('--public-ip-range', '-r',
                   action='append',
                   help='Only manage ips that fall within these ranges')
    p.add_argument('--dry-run', '-n',
                   action='store_true')
    p.add_argument('--debug',
                   action='store_const',
                   dest='level',
                   const=logging.DEBUG)

    p.set_defaults(level=logging.INFO)
    return p.parse_args()


def receive_event(data):

    try:
        event = json.loads(data)
    except ValueError:
        logging.error('failed to decode: %s', data)
        return

    if event['object']['kind'] != 'Service':
        return

    service = event['object']

    if event['type'] == 'ADDED':
        mgr.add_service(service)
    elif event['type'] == 'MODIFIED':
        mgr.remove_service(service)
        mgr.add_service(service)
    else:
        mgr.remove_service(service)


def iter_lines(fd, chunk_size=1024):
    '''Iterates over the content of a file-like object line-by-line.'''

    pending = None

    while True:
        chunk = os.read(fd.fileno(), chunk_size)
        if not chunk:
            break

        if pending is not None:
            chunk = pending + chunk
            pending = None

        lines = chunk.splitlines()

        if lines and lines[-1]:
            pending = lines.pop()

        for line in lines:
            yield line

    if pending:
        yield(pending)


def main():
    global mgr
    global args

    args = parse_args()
    logging.basicConfig(level=args.level)

    mgr = IPManager(interface=args.interface,
                    fwchain=args.firewall_chain,
                    fwmark=args.firewall_mark,
                    cidrs=args.public_ip_range)
    api = '%s/api/%s' % (args.server, args.api_version)

    try:
        while True:
            r = requests.get('%s/watch/services' % api,
                             stream=True)

            if r.ok:
                lines = iter_lines(r.raw)
                for datalen, data, marker in izip(lines, lines, lines):
                    receive_event(data)
            else:
                logging.warn('request failed (%d): %s',
                             r.status_code,
                             r.reason)


            logging.warn('reconnecting to server')
            time.sleep(5)
    finally:
        mgr.remove_all()

if __name__ == '__main__':
    main()
