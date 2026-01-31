"""
Oracle Database Connector Module
Handles connection, query execution, and data transfer with Oracle DB
"""
import oracledb
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import re


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

    def execute_script_with_substitution(self, sql: str, params: Dict = None) -> Any:
        """
        Execute a script with &parameter substitution (like SQL*Plus)

        Args:
            sql: SQL query with &param syntax
            params: Dict of parameter values

        Returns:
            Single value result
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            # Replace &param with actual values
            processed_sql = sql
            if params:
                for key, value in params.items():
                    # Handle both &param and &param. syntax
                    pattern = r'&' + re.escape(key) + r'\.?'
                    if isinstance(value, str):
                        # String values - add quotes if not already a table name
                        if key == 'cf_pattern':
                            # Table name - no quotes
                            processed_sql = re.sub(pattern, str(value), processed_sql)
                        else:
                            processed_sql = re.sub(pattern, f"'{value}'", processed_sql)
                    else:
                        processed_sql = re.sub(pattern, str(value), processed_sql)

            cursor = self.connection.cursor()
            cursor.execute(processed_sql)
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

    def write_monthly_pattern(self, run_id: str, scenario_name: str,
                              pattern_df: pd.DataFrame, table_name: str = 'CF_PATTERNS') -> int:
        """
        Write 180 monthly cashflow pattern to Oracle table

        Args:
            run_id: Unique run identifier
            scenario_name: Name of the scenario (Base or scenario name)
            pattern_df: DataFrame with monthly pattern data (180 rows)
            table_name: Target table name

        Returns:
            Number of rows written
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            # Create table if not exists
            create_sql = f"""
                BEGIN
                    EXECUTE IMMEDIATE 'CREATE TABLE {table_name} (
                        ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        RUN_ID VARCHAR2(50) NOT NULL,
                        SCENARIO_NAME VARCHAR2(100) NOT NULL,
                        MONTH_NUM NUMBER(3) NOT NULL,
                        WEIGHT NUMBER(18,10) NOT NULL,
                        CUMULATIVE_WEIGHT NUMBER(18,10),
                        CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )';
                EXCEPTION
                    WHEN OTHERS THEN
                        IF SQLCODE = -955 THEN NULL; END IF;
                END;
            """
            cursor.execute(create_sql)

            insert_sql = f"""
                INSERT INTO {table_name}
                (RUN_ID, SCENARIO_NAME, MONTH_NUM, WEIGHT, CUMULATIVE_WEIGHT, CREATED_AT)
                VALUES (:1, :2, :3, :4, :5, :6)
            """

            now = datetime.now()
            data = []
            cumulative = 0

            # Assuming pattern_df has columns like 'Period' and weight column
            weight_col = None
            for col in pattern_df.columns:
                if 'ağırlık' in col.lower() or 'weight' in col.lower():
                    weight_col = col
                    break

            if weight_col is None:
                # Try to find numeric column
                for col in pattern_df.columns:
                    if pattern_df[col].dtype in ['float64', 'int64']:
                        weight_col = col
                        break

            run_id_s = str(run_id)[:50]
            scenario_name_s = str(scenario_name)[:100]
            dec = 4
            for idx, row in pattern_df.iterrows():
                month_num = idx + 1 if isinstance(idx, int) else int(row.get('Period', idx + 1))
                month_num = min(max(1, month_num), 180)
                try:
                    v = float(row[weight_col]) if weight_col else 0.0
                    if not (v == v and abs(v) != float('inf')):
                        v = 0.0
                except (TypeError, ValueError):
                    v = 0.0
                weight = round(v, dec)
                cumulative = round(cumulative + weight, dec)
                if cumulative > 999999.9999:
                    cumulative = 999999.9999
                data.append((run_id_s, scenario_name_s, month_num, weight, round(cumulative, dec), now))

            cursor.executemany(insert_sql, data)
            self.connection.commit()

            rows_affected = cursor.rowcount
            cursor.close()

            return rows_affected
        except Exception as e:
            self.connection.rollback()
            raise Exception(f"Error writing monthly pattern: {e}")

    def write_cashflow_patterns(self, run_id: str, scenario_name: str,
                                 months: List[int], weights: List[float],
                                 table_name: str = 'CF_PATTERNS') -> int:
        """
        Write cashflow pattern data to CF_PATTERNS table (180 monthly)

        Args:
            run_id: Unique run identifier
            scenario_name: Name of the scenario (Base or scenario name)
            months: List of month numbers (1-180)
            weights: List of weight values
            table_name: Target table name

        Returns:
            Number of rows written
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            # Create table if not exists
            create_sql = f"""
                BEGIN
                    EXECUTE IMMEDIATE 'CREATE TABLE {table_name} (
                        ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        RUN_ID VARCHAR2(50) NOT NULL,
                        SCENARIO_NAME VARCHAR2(100) NOT NULL,
                        MONTH_NUM NUMBER(3) NOT NULL,
                        WEIGHT NUMBER(18,10) NOT NULL,
                        CUMULATIVE_WEIGHT NUMBER(18,10),
                        CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )';
                EXCEPTION
                    WHEN OTHERS THEN
                        IF SQLCODE = -955 THEN NULL; END IF;
                END;
            """
            cursor.execute(create_sql)

            insert_sql = f"""
                INSERT INTO {table_name}
                (RUN_ID, SCENARIO_NAME, MONTH_NUM, WEIGHT, CUMULATIVE_WEIGHT, CREATED_AT)
                VALUES (:1, :2, :3, :4, :5, :6)
            """

            now = datetime.now()
            data = []
            cumulative = 0.0
            # ORA-01438: fit NUMBER(18,10) or NUMBER(10,4); VARCHAR2 lengths
            run_id_s = str(run_id)[:50]
            scenario_name_s = str(scenario_name)[:100]
            # 4 decimals: fits NUMBER(10,4) and NUMBER(18,10); avoids ORA-01438
            dec = 4

            for month, weight in zip(months, weights):
                try:
                    v = float(weight)
                    if not (v == v and abs(v) != float('inf')):
                        v = 0.0
                except (TypeError, ValueError):
                    v = 0.0
                w = round(v, dec)
                cumulative = round(cumulative + w, dec)
                if cumulative > 999999.9999:
                    cumulative = 999999.9999
                m = int(month) if 1 <= int(month) <= 180 else min(max(1, int(month)), 180)
                data.append((run_id_s, scenario_name_s, m, w, round(cumulative, dec), now))

            cursor.executemany(insert_sql, data)
            self.connection.commit()

            rows_affected = cursor.rowcount
            cursor.close()

            return rows_affected
        except Exception as e:
            self.connection.rollback()
            raise Exception(f"Error writing cashflow patterns: {e}")

    def get_cf_pattern_table_name(self, run_id: str, scenario_name: str) -> str:
        """
        Generate a unique table name for a scenario's CF pattern

        Args:
            run_id: Run identifier
            scenario_name: Scenario name

        Returns:
            Table name string
        """
        # Clean scenario name for table naming
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', scenario_name).upper()
        return f"CF_{clean_name}_{run_id[-8:]}"

    def save_analysis_result(self, run_id: str, scenario_name: str,
                             script_name: str, result_value: float,
                             script_order: int = 0,
                             parameters: Dict = None) -> bool:
        """
        Save analysis result to ANALYSIS_RESULTS table

        Args:
            run_id: Unique run identifier
            scenario_name: Name of the scenario
            script_name: Name of the SQL script
            result_value: Calculated result value
            script_order: Execution order of the script
            parameters: Script parameters used

        Returns:
            True if successful
        """
        if not self.connection:
            raise Exception("Not connected to database")

        try:
            cursor = self.connection.cursor()

            # Create table if not exists
            create_sql = """
                BEGIN
                    EXECUTE IMMEDIATE 'CREATE TABLE ANALYSIS_RESULTS (
                        ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        RUN_ID VARCHAR2(50) NOT NULL,
                        SCENARIO_NAME VARCHAR2(100) NOT NULL,
                        SCRIPT_NAME VARCHAR2(200) NOT NULL,
                        SCRIPT_ORDER NUMBER(3),
                        RESULT_VALUE NUMBER(20,4),
                        PARAMETERS CLOB,
                        EXECUTED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )';
                EXCEPTION
                    WHEN OTHERS THEN
                        IF SQLCODE = -955 THEN NULL; END IF;
                END;
            """
            cursor.execute(create_sql)

            insert_sql = """
                INSERT INTO ANALYSIS_RESULTS
                (RUN_ID, SCENARIO_NAME, SCRIPT_NAME, SCRIPT_ORDER, RESULT_VALUE, PARAMETERS, EXECUTED_AT)
                VALUES (:1, :2, :3, :4, :5, :6, :7)
            """

            params_json = json.dumps(parameters) if parameters else None

            cursor.execute(insert_sql, (
                run_id, scenario_name, script_name, script_order,
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
            SELECT RUN_ID, SCENARIO_NAME, SCRIPT_NAME, SCRIPT_ORDER, RESULT_VALUE,
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
