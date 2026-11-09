def find_user(conn, name):
    cursor = conn.execute("SELECT id, name FROM users WHERE name LIKE ?", (f"%{name}%",))  # Partial match.
    return [list(row) for row in cursor.fetchall()]
