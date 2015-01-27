import json
import logging
import requests
import time
from multiprocessing import Process
from itertools import izip

from utils import iter_lines

default_etcd_endpoint = 'http://localhost:4001'
default_etcd_prefix = '/kube'

class AddressWatcher (Process):
    log = logging.getLogger('kiwi.addresswatcher')

    def __init__(self,
                 etcd_endpoint=default_etcd_endpoint,
                 etcd_prefix=default_etcd_prefix):
        super(AddressWatcher, self).__init__()

        self.etcd_api = '%s/v2' % etcd_endpoint
        self.etcd_prefix = etcd_prefix

    def run(self):
        while True:
            r = requests.get('%s/keys%s/publicips' % (self.etcd_api,
                                                      self.etcd_prefix),
                             params={'recursive': 'true',
                                     'wait': 'true'})
            if r.ok:
                event = r.json()
                handler = getattr(self, 'handle_%s' %
                                  event['action'].lower(), None)

                if not handler:
                    self.log.warn('unknown event: %(action)s' % event)
                    continue

                node = event['node']
                relkey = node['key'][len(self.etcd_prefix)+1:]
                handler(relkey, node)
            else:
                self.log.error('request failed (%d): %s',
                               r.status_code,
                               r.reason)
                time.sleep(5)

    def handle_create(self, relkey, node):
        try:
            dir, address = relkey.split('/')
        except ValueError:
            self.log.error('invalid create operation on: %s', relkey)
            return

        self.log.info('create: %s %s', dir, address)
    def handle_delete(self, relkey, node):
        try:
            dir, address, name = relkey.split('/')
        except ValueError:
            try:
                dir, address = relkey.split('/')
                name = '-'
            except ValueError:
                self.log.error('invalid delete operation on: %s', relkey)
                return

        self.log.info('delete: %s %s %s', dir, address, name)
    def handle_set(self, relkey, node):
        try:
            dir, address, name = relkey.split('/')
        except ValueError:
            self.log.error('invalid set operation on: %s', relkey)
            return

        self.log.info('set: %s %s %s', dir, address, name)
    def handle_expire(self, relkey, node):
        self.log.info('expire: %s %s', relkey, node)

logging.basicConfig(level=logging.DEBUG)
s = AddressWatcher()
s.run()
