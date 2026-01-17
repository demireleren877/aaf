"""
Oracle Database Connector Module
Handles connection, query execution, and data transfer with Oracle DB
"""
import oracledb
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime
import json


class OracleConnector:
    """Oracle database connection and operations handler"""

    def __init__(self):
        self.connection = None
        self.config = {}

    def connect(self, host: str, port: int, service: str, username: str, password: str) -> bool:
        """
        Establish connection to Oracle database

        Args:
            host: Oracle server hostname/IP
            port: Oracle listener port (default 1521)
            service: Oracle service name
            username: Database username
            password: Database password

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Build DSN
            dsn = oracledb.makedsn(host, port, service_name=service)

            # Connect
            self.connection = oracledb.connect(
                user=username,
                password=password,
                dsn=dsn
            )

            # Store config
            self.config = {
                'host': host,
                'port': port,
                'service': service,
                'username': username
            }

            return True
        except Exception as e:
            print(f"Oracle connection error: {e}")
            raise e

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the current connection

        Returns:
            Dict with status and server info
        """
        if not self.connection:
            return {'success': False, 'error': 'Not connected'}

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT SYSDATE, USER, ORA_DATABASE_NAME FROM DUAL")
            row = cursor.fetchone()
            cursor.close()

            return {
                'success': True,
                'server_time': row[0].isoformat() if row[0] else None,
                'user': row[1],
                'database': row[2]
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_tables(self, schema: str = None) -> List[str]:
        """
        Get list of accessible tables

        Args:
            schema: Optional schema name filter

        Returns:
            List of table names
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            if schema:
                cursor.execute("""
                    SELECT table_name FROM all_tables
                    WHERE owner = :schema
                    ORDER BY table_name
                """, {'schema': schema.upper()})
            else:
                cursor.execute("""
                    SELECT table_name FROM user_tables
                    ORDER BY table_name
                """)

            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return tables
        except Exception as e:
            raise Exception(f"Error fetching tables: {e}")

    def execute_query(self, sql: str, params: Dict = None) -> pd.DataFrame:
        """
        Execute a SELECT query and return results as DataFrame

        Args:
            sql: SQL query string
            params: Optional query parameters

        Returns:
            pandas DataFrame with results
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            # Get column names
            columns = [desc[0] for desc in cursor.description]

            # Fetch all rows
            rows = cursor.fetchall()
            cursor.close()

            return pd.DataFrame(rows, columns=columns)
        except Exception as e:
            raise Exception(f"Query execution error: {e}")

    def execute_script(self, sql: str, params: Dict = None) -> Any:
        """
        Execute a script that returns a single value

        Args:
            sql: SQL query string (should return single value)
            params: Optional query parameters

        Returns:
            Single value result
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            row = cursor.fetchone()
            cursor.close()

            return row[0] if row else None
        except Exception as e:
            raise Exception(f"Script execution error: {e}")

    def write_dataframe(self, df: pd.DataFrame, table_name: str,
                        if_exists: str = 'append') -> int:
        """
        Write DataFrame to Oracle table

        Args:
            df: pandas DataFrame to write
            table_name: Target table name
            if_exists: 'append' or 'replace'

        Returns:
            Number of rows written
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            # If replace, truncate table first
            if if_exists == 'replace':
                try:
                    cursor.execute(f"TRUNCATE TABLE {table_name}")
                except:
                    pass  # Table might not exist

            # Prepare insert statement
            columns = df.columns.tolist()
            placeholders = ', '.join([f':{i+1}' for i in range(len(columns))])
            column_str = ', '.join(columns)

            insert_sql = f"INSERT INTO {table_name} ({column_str}) VALUES ({placeholders})"

            # Convert DataFrame to list of tuples
            data = [tuple(row) for row in df.values]

            # Execute batch insert
            cursor.executemany(insert_sql, data)
            self.connection.commit()

            rows_affected = cursor.rowcount
            cursor.close()

            return rows_affected
        except Exception as e:
            self.connection.rollback()
            raise Exception(f"Error writing to table: {e}")

    def write_cashflow_patterns(self, run_id: str, scenario_name: str,
                                 quarters: List[str], weights: List[float]) -> int:
        """
        Write cashflow pattern data to CASHFLOW_PATTERNS table

        Args:
            run_id: Unique run identifier
            scenario_name: Name of the scenario (Base or scenario name)
            quarters: List of quarter labels (Q1, Q2, ...)
            weights: List of weight values

        Returns:
            Number of rows written
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            insert_sql = """
                INSERT INTO CASHFLOW_PATTERNS (RUN_ID, SCENARIO_NAME, QUARTER, WEIGHT, CREATED_AT)
                VALUES (:1, :2, :3, :4, :5)
            """

            now = datetime.now()
            data = []
            for i, (q, w) in enumerate(zip(quarters, weights)):
                quarter_num = int(q.replace('Q', ''))
                data.append((run_id, scenario_name, quarter_num, w, now))

            cursor.executemany(insert_sql, data)
            self.connection.commit()

            rows_affected = cursor.rowcount
            cursor.close()

            return rows_affected
        except Exception as e:
            self.connection.rollback()
            raise Exception(f"Error writing cashflow patterns: {e}")

    def save_analysis_result(self, run_id: str, scenario_name: str,
                             script_name: str, result_value: float,
                             parameters: Dict = None) -> bool:
        """
        Save analysis result to ANALYSIS_RESULTS table

        Args:
            run_id: Unique run identifier
            scenario_name: Name of the scenario
            script_name: Name of the SQL script
            result_value: Calculated result value
            parameters: Script parameters used

        Returns:
            True if successful
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            insert_sql = """
                INSERT INTO ANALYSIS_RESULTS
                (RUN_ID, SCENARIO_NAME, SCRIPT_NAME, RESULT_VALUE, PARAMETERS, EXECUTED_AT)
                VALUES (:1, :2, :3, :4, :5, :6)
            """

            params_json = json.dumps(parameters) if parameters else None

            cursor.execute(insert_sql, (
                run_id, scenario_name, script_name,
                result_value, params_json, datetime.now()
            ))
            self.connection.commit()
            cursor.close()

            return True
        except Exception as e:
            self.connection.rollback()
            raise Exception(f"Error saving analysis result: {e}")

    def get_analysis_history(self, limit: int = 100) -> pd.DataFrame:
        """
        Get history of analysis results

        Args:
            limit: Maximum number of results to return

        Returns:
            DataFrame with analysis history
        """
        if not self.connection:
            raise Exception("Not connected to database")

        sql = """
            SELECT RUN_ID, SCENARIO_NAME, SCRIPT_NAME, RESULT_VALUE,
                   PARAMETERS, EXECUTED_AT
            FROM ANALYSIS_RESULTS
            ORDER BY EXECUTED_AT DESC
            FETCH FIRST :limit ROWS ONLY
        """

        return self.execute_query(sql, {'limit': limit})

    def close(self):
        """Close the database connection"""
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
            self.connection = None
            self.config = {}

    def is_connected(self) -> bool:
        """Check if currently connected"""
        if not self.connection:
            return False
        try:
            # Simple ping
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.close()
            return True
        except:
            return False


# Global instance
oracle_db = OracleConnector()
