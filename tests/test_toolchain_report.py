from __future__ import annotations

import unittest

from tools.toolchain_report import install_guidance


class ToolchainReportTests(unittest.TestCase):
    def test_fedora_guidance_uses_dnf(self) -> None:
        self.assertEqual(install_guidance("fedora"), ["sudo dnf install -y fpc"])

    def test_debian_guidance_uses_apt(self) -> None:
        self.assertEqual(
            install_guidance("debian"),
            ["sudo apt-get update", "sudo apt-get install -y fp-compiler"],
        )
