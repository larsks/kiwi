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
                 queue,
                 etcd_endpoint=default_etcd_endpoint,
                 etcd_prefix=default_etcd_prefix):
        super(AddressWatcher, self).__init__()

        self.q = queue
        self.etcd_api = '%s/v2' % etcd_endpoint
        self.etcd_prefix = etcd_prefix

    def run(self):
        waitindex = 0

        while True:
            self.log.debug('watching from waitindex = %s', waitindex)
            r = requests.get('%s/keys%s/publicips' % (self.etcd_api,
                                                      self.etcd_prefix),
                             params={'recursive': 'true',
                                     'wait': 'true',
                                     'waitIndex': waitindex})
            if r.ok:
                event = r.json()
                self.log.debug('event: %s', event)
                waitindex = event['node']['modifiedIndex'] + 1

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
        self.q.put({'message': 'add-address',
                    'data': {'address': address}})

    def handle_delete(self, relkey, node):

        try:
            dir, address, name = relkey.split('/')
            self.log.info('delete lock: %s %s %s', dir, address, name)
            self.q.put({'message': 'release-lock',
                        'data': {'address': address}})
        except ValueError:
            try:
                dir, address = relkey.split('/')
                self.log.info('delete address: %s %s', dir, address)
                self.q.put({'message': 'delete-address',
                            'data': {'address': address}})
            except ValueError:
                self.log.error('invalid delete operation on: %s', relkey)
                return

    def handle_set(self, relkey, node):
        try:
            dir, address, name = relkey.split('/')
        except ValueError:
            self.log.error('invalid set operation on: %s', relkey)
            return

        owner = node['value']

        self.log.info('set: %s %s %s', dir, address, name)
        self.q.put({'message': 'acquire-lock',
                    'data': {'address': address,
                             'owner': owner}})

    def handle_expire(self, relkey, node):
        self.log.info('expire: %s %s', relkey, node)
        self.handle_delete(relkey, node)

if __name__ == '__main__':
    import multiprocessing
    logging.basicConfig(level=logging.DEBUG)

    q = multiprocessing.Queue()
    s = AddressWatcher(q)
    s.start()

    while True:
        msg = q.get()
        print 'msg:', msg

