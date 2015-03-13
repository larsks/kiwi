#!/usr/bin/python

import os
import sys
import argparse
import unittest
import mock
import subprocess

from kiwi import iptables

iptables_filter_input_output = '\n'.join([
    '-P INPUT ACCEPT',
    '-A INPUT -s 192.168.1.1 -j ACCEPT',
    '-A INPUT -s 192.168.1.0/24 -p tcp --dport 80 -j ACCEPT',
])

iptables_filter_output = '\n'.join([
    '-P INPUT ACCEPT',
    '-P FORWARD ACCEPT', 
    '-P OUTPUT ACCEPT',
    '-N testchain -',
])


class TestTables(unittest.TestCase):
    @mock.patch('subprocess.Popen')
    def test_chain_exists(self, mock_popen):
        mock_popen_return = mock.Mock()
        attrs = {
            'communicate.return_value': (iptables_filter_input_output,
                                         ''),
            'returncode': 0,
        }
        mock_popen_return.configure_mock(**attrs)
        mock_popen.configure_mock(return_value=mock_popen_return)
        assert iptables.filter.chain_exists('INPUT')
        mock_popen.assert_called_with(('iptables', '-w', '-t',
                                       'filter', '-S', 'INPUT'),
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

    @mock.patch('subprocess.Popen')
    def test_chain_does_not_exist(self, mock_popen):
        mock_popen_return = mock.Mock()
        attrs = {
            'communicate.return_value': ('\n', '\n'),
            'returncode': 1,
        }
        mock_popen_return.configure_mock(**attrs)
        mock_popen.configure_mock(return_value=mock_popen_return)
        assert not iptables.filter.chain_exists('does_not_exist')
        mock_popen.assert_called_with(('iptables', '-w', '-t',
                                       'filter', '-S', 'does_not_exist'),
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

    @mock.patch('subprocess.Popen')
    def test_list_chains(self, mock_popen):
        mock_popen_return = mock.Mock()
        attrs = {
            'communicate.return_value': (iptables_filter_output, '\n'),
            'returncode': 0,
        }
        mock_popen_return.configure_mock(**attrs)
        mock_popen.configure_mock(return_value=mock_popen_return)
        chains = tuple(iptables.filter.list_chains())
        assert chains == ('INPUT', 'FORWARD', 'OUTPUT', 'testchain')
        mock_popen.assert_called_with(('iptables', '-w', '-t',
                                       'filter', '-S'),
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

    @mock.patch('subprocess.Popen')
    def test_get_chain(self, mock_popen):
        mock_popen_return = mock.Mock()
        attrs = {
            'communicate.return_value': (iptables_filter_output, '\n'),
            'returncode': 0,
        }
        mock_popen_return.configure_mock(**attrs)
        mock_popen.configure_mock(return_value=mock_popen_return)
        chain = iptables.filter.chains['INPUT']
        assert chain.name == 'INPUT'
        mock_popen.assert_called_with(('iptables', '-w', '-t',
                                       'filter', '-S', 'INPUT'),
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

class TestChains(unittest.TestCase):
    @mock.patch('subprocess.Popen')
    def test_rule_exists(self, mock_popen):
        mock_popen_return = mock.Mock()
        attrs = {
            'communicate.return_value': (iptables_filter_output, '\n'),
            'returncode': 0,
        }
        mock_popen_return.configure_mock(**attrs)
        mock_popen.configure_mock(return_value=mock_popen_return)
        chain = iptables.filter.chains['INPUT']
        assert chain.name == 'INPUT'
        mock_popen.assert_called_with(('iptables', '-w', '-t',
                                       'filter', '-S', 'INPUT'),
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

        rule = iptables.Rule(
            '-A INPUT -s 192.168.1.0/24 -p tcp --dport 80 -j ACCEPT')
        assert chain.rule_exists(rule)
        mock_popen.assert_called_with(('iptables', '-w', '-t',
                                       'filter', '-C', 'INPUT') + rule,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

    @mock.patch('subprocess.Popen')
    def test_rule_does_not_exist(self, mock_popen):
        mock_popen_return = mock.Mock()
        attrs = {
            'communicate.return_value': (iptables_filter_output, '\n'),
            'returncode': 0,
        }
        mock_popen_return.configure_mock(**attrs)
        mock_popen.configure_mock(return_value=mock_popen_return)
        chain = iptables.filter.chains['INPUT']
        assert chain.name == 'INPUT'
        mock_popen.assert_called_with(('iptables', '-w', '-t',
                                       'filter', '-S', 'INPUT'),
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)

        rule = iptables.Rule(
            '-A INPUT -j does_not_exist')
        mock_popen_return.configure_mock(returncode=1)
        assert not chain.rule_exists(rule)
        mock_popen.assert_called_with(('iptables', '-w', '-t',
                                       'filter', '-C', 'INPUT') + rule,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
