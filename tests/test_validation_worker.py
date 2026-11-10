import io
import json
import sys
import types
import unittest
from unittest.mock import patch

from dagsmith.core.validation_worker import main


class ValidationWorkerTests(unittest.TestCase):
    def check_worker(self, bag_class):
        module = types.ModuleType('airflow.dag_processing.dagbag')
        module.DagBag = bag_class
        output = io.StringIO()
        with patch.dict(sys.modules, {'airflow.dag_processing.dagbag': module}):
            with patch('sys.stdin', io.StringIO('# candidate')), patch('sys.stdout', output):
                self.assertEqual(main(), 0)
        self.assertEqual(json.loads(output.getvalue()), {'errors': [], 'dag_count': 1})

    def test_airflow_33_constructor(self):
        class DagBag:
            def __init__(self, dag_folder=None, safe_mode=True):
                assert safe_mode is False
                self.dags = {'test': object()}
                self.import_errors = {}
        self.check_worker(DagBag)

    def test_older_constructor_disables_examples(self):
        class DagBag:
            def __init__(self, dag_folder=None, include_examples=True, safe_mode=True):
                assert include_examples is False
                assert safe_mode is False
                self.dags = {'test': object()}
                self.import_errors = {}
        self.check_worker(DagBag)


class SiblingImportTests(unittest.TestCase):
    def test_worker_can_import_sibling_module(self):
        import runpy
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "slack_helper.py").write_text("slack_notify = 42\n")
            class DagBag:
                def __init__(self, dag_folder=None, safe_mode=True):
                    result = runpy.run_path(str(Path(dag_folder, "candidate.py")))
                    assert result["slack_notify"] == 42
                    self.dags = {"example": object()}
                    self.import_errors = {}
            module = types.ModuleType("airflow.dag_processing.dagbag")
            module.DagBag = DagBag
            original_path = sys.path[:]
            try:
                with patch.dict(sys.modules, {"airflow.dag_processing.dagbag": module}), patch(
                    "sys.argv", ["worker", directory]
                ), patch("sys.stdin", io.StringIO("from slack_helper import slack_notify")), patch(
                    "sys.stdout", io.StringIO()
                ):
                    self.assertEqual(main(), 0)
            finally:
                sys.path[:] = original_path
                sys.modules.pop("slack_helper", None)
