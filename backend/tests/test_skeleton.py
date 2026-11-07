"""Skeleton sanity test for HKS."""

from __future__ import annotations

import unittest

import backend
from backend.models.types import Diagnostic, default_flags


class TestSkeleton(unittest.TestCase):
    def test_version_and_models(self) -> None:
        self.assertEqual(backend.__version__, "0.1.0")
        diag = Diagnostic(level="info", code="init", message="ok")
        self.assertEqual(diag.to_dict()["code"], "init")
        flags = default_flags()
        self.assertIn("locked", flags)
        self.assertFalse(flags["locked"])


if __name__ == "__main__":
    unittest.main()
