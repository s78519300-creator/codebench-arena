def find_user(conn, name):
    cursor = conn.execute("SELECT id, name FROM users WHERE name = ?", (name,))
    return [list(row) for row in cursor.fetchall()]
