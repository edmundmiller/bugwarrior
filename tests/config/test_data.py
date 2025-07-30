import json
import os

import pytest

from bugwarrior.config import data, schema

from ..base import ConfigTest


class TestData(ConfigTest):
    @pytest.fixture(autouse=True)
    def setup_data_test(self, setup_config_test):
        self.data = data.BugwarriorData(self.lists_path)

    def assert0600(self):
        permissions = oct(os.stat(self.data._datafile).st_mode & 0o777)
        # python2 -> 0600, python3 -> 0o600
        assert permissions in ['0600', '0o600']

    def test_get_set(self):
        # "touch" data file.
        with open(self.data._datafile, 'w+') as handle:
            json.dump({'old': 'stuff'}, handle)

        self.data.set('key', 'value')

        assert self.data.get('key') == 'value'
        assert self.data.get_data() == {'old': 'stuff', 'key': 'value'}
        self.assert0600()

    def test_set_first_time(self):
        self.data.set('key', 'value')

        assert self.data.get('key') == 'value'
        self.assert0600()

    def test_path_attribute(self):
        assert self.data.path == self.lists_path


class TestGetDataPath(ConfigTest):
    @pytest.fixture(autouse=True)
    def setup_datapath_test(self, setup_config_test):
        rawconfig = {
            'general': {'targets': ['my_service'], 'interactive': False},
            'my_service': {
                'service': 'github',
                'login': 'ralphbean',
                'token': 'abc123',
                'username': 'ralphbean',
            },
        }
        self.config = schema.validate_config(
            rawconfig, 'general', 'configpath')

    def assert_data_path(self, expected_datapath):
        assert expected_datapath == data.get_data_path(self.config['general'].taskrc)

    def test_TASKDATA(self):
        """
        TASKDATA should be respected, even when taskrc's data.location is set.
        """
        datapath = os.environ['TASKDATA'] = os.path.join(self.tempdir, 'data')
        self.assert_data_path(datapath)

    def test_taskrc_datalocation(self):
        """
        When TASKDATA is not set, data.location in taskrc should be respected.
        """
        assert 'TASKDATA' not in os.environ
        self.assert_data_path(self.lists_path)

    def test_unassigned(self):
        """
        When data path is not assigned, use default location.
        """
        # Empty taskrc.
        with open(self.taskrc, 'w'):
            pass

        assert 'TASKDATA' not in os.environ

        self.assert_data_path(os.path.expanduser('~/.task'))
