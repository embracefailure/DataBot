import json 
import httpx
from typing import Any 
import pymysql
import csv
from mcp.server.fastmcp import FastMCP
from decimal import Decimal

mcp = FastMCP("SQLServer")
USER_AGENT = "SQLserver-app/1.0"

def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

@mcp.tool()
async def sql_inter(sql_query):
    """
    Execute a SQL query on a MYSQL database and return the results.
    :param sql_query: The SQL query to execute.
    :return: The results of the SQL query.
    """

    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='123',
        database='school',
        charset ='utf8'
    )

    try:
        with connection.cursor() as cursor:
            sql = sql_query
            cursor.execute(sql)

            results = cursor.fetchall()
            

    finally:
        connection.close()

    return json.dumps(results, default=_decimal_default, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport='stdio')
