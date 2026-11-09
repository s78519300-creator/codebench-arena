def find_user(conn, name):
    cursor = conn.execute(f"SELECT id, name FROM users WHERE name = '{name}'")  # SQL injection.
    return [list(row) for row in cursor.fetchall()]
