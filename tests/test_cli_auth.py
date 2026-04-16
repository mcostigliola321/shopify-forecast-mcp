"""Tests for the shopify-forecast auth CLI subcommand."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from shopify_forecast_mcp.cli import build_parser, _run_auth


class TestAuthSubcommand:
    def test_parser_has_auth(self):
        """auth subcommand exists with --store argument."""
        parser = build_parser()
        args = parser.parse_args(["auth", "--store", "test.myshopify.com"])
        assert args.command == "auth"
        assert args.store == "test.myshopify.com"

    @patch("shopify_forecast_mcp.cli.shutil.which", return_value=None)
    def test_auth_cli_not_found(self, mock_which):
        """Returns 1 with error when shopify CLI not on PATH."""
        parser = build_parser()
        args = parser.parse_args(["auth", "--store", "test.myshopify.com"])
        result = _run_auth(args)
        assert result == 1

    @patch("shopify_forecast_mcp.cli.shutil.which", return_value="/usr/local/bin/shopify")
    @patch("shopify_forecast_mcp.cli.subprocess.run")
    def test_auth_success(self, mock_run, mock_which):
        """Runs shopify store auth with correct scopes, then verifies."""
        # First call: auth (success)
        auth_result = MagicMock(returncode=0)
        # Second call: verify (success)
        verify_stdout = json.dumps({"data": {"shop": {"ianaTimezone": "America/New_York"}}})
        verify_result = MagicMock(returncode=0, stdout=verify_stdout, stderr="")

        mock_run.side_effect = [auth_result, verify_result]

        parser = build_parser()
        args = parser.parse_args(["auth", "--store", "test.myshopify.com"])
        result = _run_auth(args)

        assert result == 0
        # Verify the auth command included correct scopes
        auth_call = mock_run.call_args_list[0]
        cmd = auth_call[0][0]
        assert "shopify" in cmd
        assert "store" in cmd
        assert "auth" in cmd
        assert "--scopes" in cmd
        scopes_idx = cmd.index("--scopes")
        scopes_str = cmd[scopes_idx + 1]
        assert "read_orders" in scopes_str
        assert "read_all_orders" in scopes_str
        assert "read_products" in scopes_str
        assert "read_inventory" in scopes_str

    @patch("shopify_forecast_mcp.cli.shutil.which", return_value="/usr/local/bin/shopify")
    @patch("shopify_forecast_mcp.cli.subprocess.run")
    def test_auth_failed(self, mock_run, mock_which):
        """Returns 1 when shopify store auth fails."""
        mock_run.return_value = MagicMock(returncode=1)
        parser = build_parser()
        args = parser.parse_args(["auth", "--store", "test.myshopify.com"])
        result = _run_auth(args)
        assert result == 1
