"""Custom Django TEST_RUNNER to execute pytest when running `python manage.py test`."""
import sys


class PytestTestRunner:
    """Test runner that delegates test execution to pytest."""

    def __init__(self, verbosity=1, failfast=False, keepdb=False, **kwargs):
        self.verbosity = verbosity
        self.failfast = failfast
        self.keepdb = keepdb

    def run_tests(self, test_labels, **kwargs):
        import pytest

        args = []
        if self.verbosity == 0:
            args.append("-q")
        elif self.verbosity >= 2:
            args.append("-v")
        if self.failfast:
            args.append("-x")

        if test_labels:
            args.extend(test_labels)
        else:
            args.append("apps")

        return pytest.main(args)
