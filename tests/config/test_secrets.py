from bugwarrior.config import secrets


class TestOracleEval:

    def test_echo(self):
        assert secrets.oracle_eval("echo fööbår") == "fööbår"
