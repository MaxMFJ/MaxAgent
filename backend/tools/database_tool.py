"""
Database Tool - 数据库操作
支持 SQLite、PostgreSQL、MySQL
"""

import os
import asyncio
import sqlite3
from typing import Optional, Dict, Any, List
from .base import BaseTool, ToolResult, ToolCategory


class DatabaseTool(BaseTool):
    """数据库操作工具"""
    
    name = "database"
    description = "数据库操作：查询、创建表、插入数据"
    category = ToolCategory.APPLICATION
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "connect", "query", "execute", "list_tables",
                    "describe_table", "backup", "create_table", "insert"
                ],
                "description": "数据库操作"
            },
            "db_type": {
                "type": "string",
                "enum": ["sqlite", "postgresql", "mysql"],
                "description": "数据库类型"
            },
            "connection_string": {
                "type": "string",
                "description": "连接字符串（SQLite 为文件路径）"
            },
            "sql": {
                "type": "string",
                "description": "SQL 语句"
            },
            "table_name": {
                "type": "string",
                "description": "表名"
            },
            "columns": {
                "type": "object",
                "description": "列定义（创建表时使用）"
            },
            "data": {
                "type": "object",
                "description": "要插入的数据"
            },
            "backup_path": {
                "type": "string",
                "description": "备份文件路径"
            }
        },
        "required": ["action"]
    }
    
    # 存储活动连接
    _connections: Dict[str, Any] = {}
    
    async def execute(
        self,
        action: str,
        db_type: str = "sqlite",
        connection_string: Optional[str] = None,
        sql: Optional[str] = None,
        table_name: Optional[str] = None,
        columns: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        backup_path: Optional[str] = None
    ) -> ToolResult:
        """执行数据库操作"""
        
        # SQLite 是默认和最简单的选项
        if db_type == "sqlite":
            return await self._sqlite_operation(
                action, connection_string, sql, table_name,
                columns, data, backup_path
            )
        elif db_type == "postgresql":
            return await self._postgres_operation(
                action, connection_string, sql, table_name
            )
        elif db_type == "mysql":
            return await self._mysql_operation(
                action, connection_string, sql, table_name
            )
        else:
            return ToolResult(success=False, error=f"不支持的数据库类型: {db_type}")
    
    async def _sqlite_operation(
        self,
        action: str,
        db_path: Optional[str],
        sql: Optional[str],
        table_name: Optional[str],
        columns: Optional[Dict[str, str]],
        data: Optional[Dict[str, Any]],
        backup_path: Optional[str]
    ) -> ToolResult:
        """SQLite 操作"""
        
        # 默认数据库路径
        if not db_path:
            db_path = "/tmp/agent_database.db"
        
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if action == "connect":
                return ToolResult(success=True, data={
                    "message": f"已连接到 SQLite: {db_path}",
                    "path": db_path
                })
            
            elif action == "query":
                if not sql:
                    return ToolResult(success=False, error="需要 SQL 查询")
                
                cursor.execute(sql)
                rows = cursor.fetchall()
                
                # 转换为字典列表
                if rows:
                    columns_names = [description[0] for description in cursor.description]
                    results = [dict(zip(columns_names, row)) for row in rows]
                else:
                    results = []
                
                return ToolResult(success=True, data={
                    "results": results,
                    "row_count": len(results)
                })
            
            elif action == "execute":
                if not sql:
                    return ToolResult(success=False, error="需要 SQL 语句")
                
                cursor.execute(sql)
                conn.commit()
                
                return ToolResult(success=True, data={
                    "message": "SQL 执行成功",
                    "rows_affected": cursor.rowcount
                })
            
            elif action == "list_tables":
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = [row[0] for row in cursor.fetchall()]
                
                return ToolResult(success=True, data={"tables": tables})
            
            elif action == "describe_table":
                if not table_name:
                    return ToolResult(success=False, error="需要表名")
                
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns_info = cursor.fetchall()
                
                schema = [
                    {
                        "cid": row[0],
                        "name": row[1],
                        "type": row[2],
                        "notnull": row[3],
                        "default_value": row[4],
                        "pk": row[5]
                    }
                    for row in columns_info
                ]
                
                return ToolResult(success=True, data={
                    "table": table_name,
                    "columns": schema
                })
            
            elif action == "create_table":
                if not table_name or not columns:
                    return ToolResult(success=False, error="需要表名和列定义")
                
                # 构建 CREATE TABLE 语句
                cols = ", ".join(
                    f"{col_name} {col_type}"
                    for col_name, col_type in columns.items()
                )
                create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({cols})"
                
                cursor.execute(create_sql)
                conn.commit()
                
                return ToolResult(success=True, data={
                    "message": f"表 {table_name} 创建成功",
                    "sql": create_sql
                })
            
            elif action == "insert":
                if not table_name or not data:
                    return ToolResult(success=False, error="需要表名和数据")
                
                cols = ", ".join(data.keys())
                placeholders = ", ".join(["?" for _ in data])
                values = list(data.values())
                
                insert_sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
                cursor.execute(insert_sql, values)
                conn.commit()
                
                return ToolResult(success=True, data={
                    "message": "数据插入成功",
                    "last_rowid": cursor.lastrowid
                })
            
            elif action == "backup":
                if not backup_path:
                    backup_path = db_path + ".backup"
                
                backup_conn = sqlite3.connect(backup_path)
                conn.backup(backup_conn)
                backup_conn.close()
                
                return ToolResult(success=True, data={
                    "message": f"数据库已备份到 {backup_path}",
                    "backup_path": backup_path
                })
            
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
            
        except sqlite3.Error as e:
            return ToolResult(success=False, error=f"SQLite 错误: {str(e)}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            if 'conn' in locals():
                conn.close()
    
    async def _postgres_operation(
        self,
        action: str,
        connection_string: Optional[str],
        sql: Optional[str],
        table_name: Optional[str]
    ) -> ToolResult:
        """PostgreSQL 操作"""
        try:
            import asyncpg
        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 asyncpg: pip install asyncpg"
            )
        
        if not connection_string:
            return ToolResult(success=False, error="需要连接字符串")
        
        try:
            conn = await asyncpg.connect(connection_string)
            
            if action == "connect":
                await conn.close()
                return ToolResult(success=True, data={"message": "PostgreSQL 连接成功"})
            
            elif action == "query":
                if not sql:
                    return ToolResult(success=False, error="需要 SQL 查询")
                
                rows = await conn.fetch(sql)
                results = [dict(row) for row in rows]
                
                await conn.close()
                return ToolResult(success=True, data={
                    "results": results,
                    "row_count": len(results)
                })
            
            elif action == "execute":
                if not sql:
                    return ToolResult(success=False, error="需要 SQL 语句")
                
                result = await conn.execute(sql)
                await conn.close()
                
                return ToolResult(success=True, data={
                    "message": "SQL 执行成功",
                    "result": result
                })
            
            elif action == "list_tables":
                rows = await conn.fetch("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                tables = [row['table_name'] for row in rows]
                
                await conn.close()
                return ToolResult(success=True, data={"tables": tables})
            
            elif action == "describe_table":
                if not table_name:
                    return ToolResult(success=False, error="需要表名")
                
                rows = await conn.fetch(f"""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}'
                """)
                
                schema = [dict(row) for row in rows]
                await conn.close()
                
                return ToolResult(success=True, data={
                    "table": table_name,
                    "columns": schema
                })
            
            else:
                await conn.close()
                return ToolResult(success=False, error=f"PostgreSQL 不支持: {action}")
            
        except Exception as e:
            return ToolResult(success=False, error=f"PostgreSQL 错误: {str(e)}")
    
    async def _mysql_operation(
        self,
        action: str,
        connection_string: Optional[str],
        sql: Optional[str],
        table_name: Optional[str]
    ) -> ToolResult:
        """MySQL 操作"""
        try:
            import aiomysql
        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 aiomysql: pip install aiomysql"
            )
        
        if not connection_string:
            return ToolResult(success=False, error="需要连接字符串")
        
        # 解析连接字符串: mysql://user:password@host:port/database
        import re
        match = re.match(
            r'mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)',
            connection_string
        )
        
        if not match:
            return ToolResult(
                success=False,
                error="连接字符串格式: mysql://user:password@host:port/database"
            )
        
        user, password, host, port, database = match.groups()
        
        try:
            conn = await aiomysql.connect(
                host=host,
                port=int(port),
                user=user,
                password=password,
                db=database
            )
            
            cursor = await conn.cursor(aiomysql.DictCursor)
            
            if action == "connect":
                await cursor.close()
                conn.close()
                return ToolResult(success=True, data={"message": "MySQL 连接成功"})
            
            elif action == "query":
                if not sql:
                    return ToolResult(success=False, error="需要 SQL 查询")
                
                await cursor.execute(sql)
                rows = await cursor.fetchall()
                
                await cursor.close()
                conn.close()
                
                return ToolResult(success=True, data={
                    "results": rows,
                    "row_count": len(rows)
                })
            
            elif action == "execute":
                if not sql:
                    return ToolResult(success=False, error="需要 SQL 语句")
                
                await cursor.execute(sql)
                await conn.commit()
                
                await cursor.close()
                conn.close()
                
                return ToolResult(success=True, data={
                    "message": "SQL 执行成功",
                    "rows_affected": cursor.rowcount
                })
            
            elif action == "list_tables":
                await cursor.execute("SHOW TABLES")
                rows = await cursor.fetchall()
                tables = [list(row.values())[0] for row in rows]
                
                await cursor.close()
                conn.close()
                
                return ToolResult(success=True, data={"tables": tables})
            
            elif action == "describe_table":
                if not table_name:
                    return ToolResult(success=False, error="需要表名")
                
                await cursor.execute(f"DESCRIBE {table_name}")
                rows = await cursor.fetchall()
                
                await cursor.close()
                conn.close()
                
                return ToolResult(success=True, data={
                    "table": table_name,
                    "columns": rows
                })
            
            else:
                await cursor.close()
                conn.close()
                return ToolResult(success=False, error=f"MySQL 不支持: {action}")
            
        except Exception as e:
            return ToolResult(success=False, error=f"MySQL 错误: {str(e)}")
