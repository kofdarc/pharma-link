"""
Unit tests for the pharmacy-side connector agent (pharmalink_connector.py).

Runs with the stdlib unittest runner only, in keeping with the connector's own
"stdlib only" constraint (it has to run on a bare Python install on a counter PC
with no pip access):

    python3 -m unittest tools/connector/test_pharmalink_connector.py -v

The mssql tests fake out `pyodbc` via sys.modules rather than requiring it
installed, since pyodbc is an optional dependency only needed by pharmacies that
actually configure a SQL Server source.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pharmalink_connector as connector  # noqa: E402


class SignRequestTests(unittest.TestCase):
    def test_signature_is_deterministic_for_identical_inputs(self):
        with mock.patch("time.time", return_value=1000), mock.patch("uuid.uuid4") as fake_uuid:
            fake_uuid.return_value.hex = "abc123"
            headers_a = connector.sign_request(secret="s3cret", method="post", path="/x", body=b"{}")
            headers_b = connector.sign_request(secret="s3cret", method="post", path="/x", body=b"{}")
        self.assertEqual(headers_a, headers_b)
        self.assertEqual(headers_a["X-PharmaLink-Nonce"], "abc123")

    def test_signature_changes_with_secret(self):
        headers_a = connector.sign_request(secret="one", method="POST", path="/x", body=b"{}")
        headers_b = connector.sign_request(secret="two", method="POST", path="/x", body=b"{}")
        self.assertNotEqual(headers_a["X-PharmaLink-Signature"], headers_b["X-PharmaLink-Signature"])


class CsvSourceTests(unittest.TestCase):
    def test_reads_and_remaps_columns_and_skips_blank_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stock.csv"
            path.write_text(
                "code,description,qty_on_hand,retail_price\nABC,Panadol,10,2.5\n,Ignored,5,1\n",
                encoding="utf-8",
            )
            rows = connector.read_csv_source(
                {
                    "path": str(path),
                    "columns": {
                        "external_code": "code",
                        "name": "description",
                        "quantity": "qty_on_hand",
                        "selling_price": "retail_price",
                    },
                }
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_code"], "ABC")
        self.assertEqual(rows[0]["name"], "Panadol")
        self.assertEqual(rows[0]["quantity"], 10)
        self.assertEqual(rows[0]["selling_price"], 2.5)

    def test_missing_file_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            connector.read_csv_source({"path": "/nonexistent/path.csv"})


class SqliteSourceTests(unittest.TestCase):
    def test_reads_rows_via_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "pos.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE items (item_code TEXT, item_name TEXT, stock_qty INTEGER, price REAL)")
            conn.execute("INSERT INTO items VALUES ('X1', 'Aspirin', 20, 3.0)")
            conn.commit()
            conn.close()
            rows = connector.read_sqlite_source(
                {
                    "path": str(db_path),
                    "query": "SELECT item_code AS external_code, item_name AS name, stock_qty AS quantity, price AS selling_price FROM items",
                }
            )
        self.assertEqual(
            rows,
            [
                {
                    "external_code": "X1",
                    "name": "Aspirin",
                    "quantity": 20,
                    "selling_price": 3.0,
                    "purchase_cost": None,
                    "expiry_date": None,
                    "supplier_name": "",
                }
            ],
        )

    def test_missing_database_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            connector.read_sqlite_source({"path": "/nonexistent/pos.db", "query": "SELECT 1"})


class DeltaTests(unittest.TestCase):
    def test_unchanged_row_is_skipped(self):
        row = {"external_code": "A1", "quantity": 5, "selling_price": 1.0, "purchase_cost": 0.5, "expiry_date": None}
        snapshot = {"A1": connector.row_fingerprint(row)}
        changed, _ = connector.compute_delta([row], snapshot)
        self.assertEqual(changed, [])

    def test_changed_quantity_is_included(self):
        row = {"external_code": "A1", "quantity": 5, "selling_price": 1.0, "purchase_cost": 0.5, "expiry_date": None}
        changed, _ = connector.compute_delta([row], {"A1": "stale-digest"})
        self.assertEqual(changed, [row])

    def test_item_dropped_from_source_is_zeroed_out(self):
        changed, new_snapshot = connector.compute_delta([], {"GONE": "digest"})
        self.assertEqual(changed, [{"external_code": "GONE", "quantity": 0, "name": ""}])
        self.assertEqual(new_snapshot, {})


class MssqlSourceTests(unittest.TestCase):
    def _install_fake_pyodbc(self, rows, description):
        fake_module = mock.MagicMock()
        fake_cursor = mock.MagicMock()
        fake_cursor.description = description
        fake_cursor.fetchall.return_value = rows
        fake_connection = mock.MagicMock()
        fake_connection.cursor.return_value = fake_cursor
        fake_module.connect.return_value = fake_connection
        sys.modules["pyodbc"] = fake_module
        self.addCleanup(sys.modules.pop, "pyodbc", None)
        return fake_module, fake_connection

    def test_missing_pyodbc_raises_clear_error(self):
        with mock.patch.dict(sys.modules, {"pyodbc": None}):
            with self.assertRaises(SystemExit) as ctx:
                connector.read_mssql_source({"server": "s", "database": "d", "query": "SELECT 1"})
        self.assertIn("pyodbc", str(ctx.exception))

    def test_trusted_connection_used_by_default(self):
        fake_module, fake_connection = self._install_fake_pyodbc(
            rows=[("X1", "Aspirin", 5, 3.0, 1.0, None, "Acme")],
            description=[(name,) for name in ("external_code", "name", "quantity", "selling_price", "purchase_cost", "expiry_date", "supplier_name")],
        )
        rows = connector.read_mssql_source({"server": "SRV", "database": "SoftPharmDB", "query": "SELECT 1"})
        connection_string = fake_module.connect.call_args[0][0]
        self.assertIn("Trusted_Connection=yes", connection_string)
        self.assertNotIn("UID=", connection_string)
        self.assertEqual(rows[0]["external_code"], "X1")
        fake_connection.close.assert_called_once()

    def test_username_password_used_when_provided(self):
        fake_module, _ = self._install_fake_pyodbc(rows=[], description=[])
        with mock.patch.dict(os.environ, {"PHARMALINK_SQL_PASSWORD": "secret-pw"}):
            connector.read_mssql_source({"server": "SRV", "database": "DB", "username": "reader", "query": "SELECT 1"})
        connection_string = fake_module.connect.call_args[0][0]
        self.assertIn("UID=reader", connection_string)
        self.assertIn("PWD=secret-pw", connection_string)
        self.assertNotIn("Trusted_Connection", connection_string)

    def test_rows_missing_external_code_are_skipped(self):
        self._install_fake_pyodbc(
            rows=[(None, "No code", 1, 1.0, 1.0, None, "")],
            description=[(name,) for name in ("external_code", "name", "quantity", "selling_price", "purchase_cost", "expiry_date", "supplier_name")],
        )
        rows = connector.read_mssql_source({"server": "s", "database": "d", "query": "SELECT 1"})
        self.assertEqual(rows, [])


class ReadSourceDispatchTests(unittest.TestCase):
    def test_unsupported_type_raises(self):
        with self.assertRaises(SystemExit):
            connector.read_source({"type": "carrier-pigeon"})


if __name__ == "__main__":
    unittest.main()
