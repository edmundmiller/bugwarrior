import abc
import os.path

import pytest
import responses

from bugwarrior import config
from bugwarrior.config import schema


class AbstractServiceTest(abc.ABC):
    """ Ensures that certain test methods are implemented for each service. """
    @abc.abstractmethod
    def test_to_taskwarrior(self):
        """ Test Service.to_taskwarrior(). """
        raise NotImplementedError

    @abc.abstractmethod
    def test_issues(self):
        """
        Test Service.issues().

        - When the API is accessed via requests, use the responses library to
        mock requests.
        - When the API is accessed via a third party library, substitute a fake
        implementation class for it.
        """
        raise NotImplementedError


class ConfigTest:
    """
    Creates config files, configures the environment, and cleans up afterwards.
    """

    @pytest.fixture(autouse=True)
    def setup_config_test(self, caplog, tmp_path):
        self.caplog = caplog
        self.old_environ = os.environ.copy()
        self.tempdir = str(tmp_path)

        # Create temporary config files.
        self.taskrc = os.path.join(self.tempdir, '.taskrc')
        self.lists_path = os.path.join(self.tempdir, 'lists')
        os.mkdir(self.lists_path)
        with open(self.taskrc, 'w+') as fout:
            fout.write('data.location=%s\n' % self.lists_path)

        # Configure environment.
        os.environ['HOME'] = self.tempdir
        os.environ['XDG_CONFIG_HOME'] = os.path.join(self.tempdir, '.config')
        os.environ.pop(config.BUGWARRIORRC, None)
        os.environ.pop('TASKRC', None)
        os.environ.pop('XDG_CONFIG_DIRS', None)

        yield

        # Cleanup
        os.environ = self.old_environ

    def validate(self):
        self.config['general'] = self.config.get('general', {})
        self.config['general']['interactive'] = False
        return schema.validate_config(self.config, 'general', 'configpath')

    def assert_validation_error(self, expected):
        with pytest.raises(SystemExit):
            self.validate()

        # Only one message should be logged.
        assert len(self.caplog.records) == 1
        assert expected in self.caplog.records[0].message

        # We may want to use this assertion more than once per test.
        self.caplog.clear()


class ServiceTest(ConfigTest):
    GENERAL_CONFIG = {
        'interactive': False,
        'annotation_length': 100,
        'description_length': 100,
    }
    SERVICE_CONFIG = {
    }

    def get_mock_service(
        self, service_class, section='unspecified',
        config_overrides=None, general_overrides=None
    ):
        options = {
            'general': {**self.GENERAL_CONFIG, 'targets': [section]},
            section: {**self.SERVICE_CONFIG.copy(), 'target': section},
        }
        if config_overrides:
            options[section].update(config_overrides)
        if general_overrides:
            options['general'].update(general_overrides)

        service_config = service_class.CONFIG_SCHEMA(**options[section])
        main_config = schema.MainSectionConfig(**options['general'])

        return service_class(service_config, main_config)

    @staticmethod
    def add_response(url, method='GET', **kwargs):
        responses.add(responses.Response(
            url=url,
            method=method,
            match_querystring=True,
            **kwargs
        ))
