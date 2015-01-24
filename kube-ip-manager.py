#!/usr/bin/python

import os
import sys
import argparse
import json
import subprocess
import logging
import time

from contextlib import closing

class IPManager (object):
    log = logging.getLogger('ipmanager')

    def __init__(self, interface):
        self.interface = interface
        self.pips = {}

    def add_service(self, service):
        for ip in service.get('publicIPs', []):
            self.log.info('add service %s at %s',
                          service['id'], ip)
            if ip not in self.pips:
                self.pips[ip] = 1
                self.add_ip_address(ip)
            else:
                self.pips[ip] += 1

    def remove_service(self, service):
        for ip in service.get('publicIPs', []):
            self.log.info('remove service %s at %s',
                          service['id'], ip)
            self.pips[ip] -= 1
            if self.pips[ip] == 0:
                del self.pips[ip]
                self.remove_ip_address(ip)
    
    def add_ip_address(self, ip):
        self.log.info('adding address %s to interface %s',
                      ip, self.interface)
        p = subprocess.Popen(['ip', 'addr', 'add',
                               '%s/32' % ip, 'dev', self.interface],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        out, err = p.communicate()

        if p.returncode != 0:
            self.log.warn('failed to add address %s to interface %s '
                          '(returncode=%d): %s',
                          ip, self.interface, p.returncode, err)

    def remove_ip_address(self, ip):
        self.log.info('removing address %s from interface %s',
                      ip, self.interface)
        p = subprocess.Popen(['ip', 'addr', 'del',
                               '%s/32' % ip, 'dev', self.interface],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        out, err = p.communicate()

        if p.returncode != 0:
            self.log.warn('failed to remove address %s from interface %s '
                          '(returncode=%d): %s',
                          ip, self.interface, p.returncode, err)


    def remove_all(self):
        for ip in self.pips.keys():
            self.remove_ip_address(ip)

        self.pips = {}

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
    return p.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)

    mgr = IPManager(args.interface)
    api = '%s/api/%s' % (args.server, args.api_version)

    try:
        while True:
            # I'm using 'curl' here rather than requests with stream=true
            # because requests seemed to have a buffering issue that was
            # making it run behind by one event.
            p = subprocess.Popen(['curl', '-sfN', 
                                  '%s/watch/services' % api],
                                 stdout=subprocess.PIPE,
                                 bufsize=1)

            for line in iter(p.stdout.readline, b''):
                event = json.loads(line)
                if event['object']['kind'] != 'Service':
                    continue

                service = event['object']

                if event['type'] == 'ADDED':
                    mgr.add_service(service)
                else:
                    mgr.remove_service(service)

            out, err = p.communicate()
            logging.warn('curl failed (returncode=%d); sleeping before retry',
                         p.returncode)
            time.sleep(5)
    finally:
        mgr.remove_all()

if __name__ == '__main__':
    main()
