#!/usr/bin/python

import os
import sys
import argparse
import logging

from multiprocessing import Queue

import manager
import addresswatcher
import servicewatcher
import defaults
import interface
import firewall

LOG = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument('--agent-id', '--id')
    p.add_argument('--refresh-interval',
                   default=defaults.refresh_interval,
                   type=int)
    p.add_argument('--reconnect-interval',
                   default=defaults.reconnect_interval,
                   type=int)

    g = p.add_argument_group('API endpoints')
    g.add_argument('--kube-endpoint', '-k',
                   default=defaults.kube_endpoint)
    g.add_argument('--etcd-endpoint', '-s',
                   default=defaults.etcd_endpoint)
    g.add_argument('--etcd-prefix', '-p',
                   default=defaults.etcd_prefix)

    g = p.add_argument_group('Network options')
    g.add_argument('--interface', '-i',
                   default=defaults.interface)
    g.add_argument('--fwchain',
                   default=defaults.fwchain)
    g.add_argument('--fwmark',
                   type=int,
                   default=defaults.fwmark)
    g.add_argument('--cidr-range', '-r',
                   action='append')
    g.add_argument('--no-driver', '-n',
                   action='store_true')

    g = p.add_argument_group('Logging options')
    g.add_argument('--verbose', '-v',
                   action='store_const',
                   const=logging.INFO,
                   dest='loglevel')
    g.add_argument('--debug', '-d',
                   action='store_const',
                   const=logging.DEBUG,
                   dest='loglevel')
    g.add_argument('--debug-requests',
                   action='store_true')

    p.set_defaults(loglevel=logging.WARN)

    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=args.loglevel,
        format='%(name)s [%(process)d] %(levelname)s %(message)s')

    if args.loglevel and not args.debug_requests:
        logging.getLogger('requests').setLevel(logging.WARN)

    LOG.info('Starting up')
    LOG.info('Kubernetes is %s', args.kube_endpoint)
    LOG.info('Etcd is %s', args.etcd_endpoint)
    LOG.info('Managing interface %s', args.interface)

    if args.no_driver:
        iface_driver = None
        fw_driver = None
    else:
        iface_driver = interface.Interface(args.interface)
        fw_driver = firewall.Firewall(fwchain=args.fwchain,
                                      fwmark=args.fwmark)

    mqueue = Queue()
    mgr = manager.Manager(mqueue,
                          etcd_endpoint=args.etcd_endpoint,
                          kube_endpoint=args.kube_endpoint,
                          etcd_prefix=args.etcd_prefix,
                          iface_driver=iface_driver,
                          fw_driver=fw_driver,
                          cidr_ranges=args.cidr_range,
                          refresh_interval=args.refresh_interval,
                          id=args.agent_id)

    LOG.info('My id is: %s', mgr.id)

    workers = [addresswatcher.AddressWatcher(mqueue,
                                             etcd_endpoint=args.etcd_endpoint,
                                             etcd_prefix=args.etcd_prefix),
               servicewatcher.ServiceWatcher(mqueue,
                                             kube_endpoint=args.kube_endpoint)]

    for worker in workers:
        worker.start()

    try:
        mgr.run()
    finally:
        mgr.cleanup()

if __name__ == '__main__':
    main()
