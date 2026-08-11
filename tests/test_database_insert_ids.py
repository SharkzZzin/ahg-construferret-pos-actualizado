from __future__ import annotations

import unittest

from ahg_pos.database import Database


class _ReturningCursor:
    lastrowid = None

    def fetchone(self):
        return {"id": 412}


class _PostgresConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]):
        self.calls.append((sql, params))
        return _ReturningCursor()


class DatabaseInsertIdTests(unittest.TestCase):
    def test_postgres_insert_reads_the_id_from_the_same_statement(self) -> None:
        database = Database("postgresql://test.invalid/database")
        connection = _PostgresConnection()
        database.conn = connection

        saved_id = database.insert_and_get_id(
            "INSERT INTO invoices(en_ncf) VALUES (?)",
            ("E320000000412",),
        )

        self.assertEqual(saved_id, 412)
        self.assertEqual(len(connection.calls), 1)
        sql, params = connection.calls[0]
        self.assertIn("VALUES (%s) RETURNING id", sql)
        self.assertNotIn("LASTVAL", sql.upper())
        self.assertEqual(params, ("E320000000412",))


if __name__ == "__main__":
    unittest.main()
