from db.connection import get_connection, get_cursor


def test_connection():
    """Test that a database connection can be established."""
    conn = get_connection()
    assert conn is not None
    assert conn.closed == 0
    conn.close()


def test_get_cursor():
    """Test that a cursor can be created and a simple query executed."""
    with get_cursor() as cursor:
        cursor.execute("SELECT 1 AS result;")
        result = cursor.fetchone()
        assert result["result"] == 1


def test_tables_exist():
    """Test that all expected tables exist in the database."""
    expected_tables = [
        "products",
        "variants",
        "customers",
        "orders",
        "order_items",
        "inventory",
    ]
    with get_cursor() as cursor:
        for table in expected_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = %(table)s
                );
            """, {"table": table})
            result = cursor.fetchone()
            assert result["exists"] is True, f"Table '{table}' does not exist."