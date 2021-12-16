import mysql.connector

def query(mysql_client: mysql.connector.MySQLConnection, query):
    cursor = mysql_client.cursor(dictionary=True)

    cursor.execute(query)

    results = []
    for row in cursor:
        results.append(row)

    cursor.close()
    mysql_client.commit()

    return results
