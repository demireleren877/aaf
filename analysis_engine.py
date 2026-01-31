"""
Analysis Engine Module
Handles batch execution of SQL scripts and result comparison
"""
import json
import uuid
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


SCRIPTS_FILE = Path(__file__).parent / 'scripts.json'


class ScriptManager:
    """Manages SQL script definitions"""

    def __init__(self):
        self.scripts = []
        self.load_scripts()

    def load_scripts(self):
        """Load scripts from JSON file"""
        try:
            if SCRIPTS_FILE.exists():
                with open(SCRIPTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.scripts = data.get('scripts', [])
        except Exception as e:
            print(f"Error loading scripts: {e}")
            self.scripts = []

    def save_scripts(self):
        """Save scripts to JSON file"""
        try:
            with open(SCRIPTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({'scripts': self.scripts}, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving scripts: {e}")
            return False

    def get_all(self) -> List[Dict]:
        """Get all scripts"""
        return self.scripts

    def get_by_id(self, script_id: str) -> Optional[Dict]:
        """Get script by ID"""
        for script in self.scripts:
            if script['id'] == script_id:
                return script
        return None

    def add(self, script: Dict) -> Dict:
        """Add new script"""
        # Generate ID if not provided
        if 'id' not in script or not script['id']:
            script['id'] = str(uuid.uuid4())[:8]

        script['created_at'] = datetime.now().isoformat()
        script['updated_at'] = script['created_at']

        self.scripts.append(script)
        self.save_scripts()
        return script

    def update(self, script_id: str, updates: Dict) -> Optional[Dict]:
        """Update existing script"""
        for i, script in enumerate(self.scripts):
            if script['id'] == script_id:
                # Preserve id and created_at
                updates['id'] = script_id
                updates['created_at'] = script.get('created_at', datetime.now().isoformat())
                updates['updated_at'] = datetime.now().isoformat()

                self.scripts[i] = updates
                self.save_scripts()
                return updates
        return None

    def delete(self, script_id: str) -> bool:
        """Delete script"""
        for i, script in enumerate(self.scripts):
            if script['id'] == script_id:
                del self.scripts[i]
                self.save_scripts()
                return True
        return False

    def reorder(self, script_ids: List[str]) -> bool:
        """Reorder scripts by given ID list"""
        new_order = []
        for sid in script_ids:
            script = self.get_by_id(sid)
            if script:
                new_order.append(script)

        # Add any remaining scripts not in the list
        for script in self.scripts:
            if script['id'] not in script_ids:
                new_order.append(script)

        self.scripts = new_order
        self.save_scripts()
        return True


class AnalysisEngine:
    """Executes analysis scripts and compares results"""

    def __init__(self, oracle_connector=None):
        self.oracle = oracle_connector
        self.script_manager = ScriptManager()

    def set_connector(self, connector):
        """Set Oracle connector"""
        self.oracle = connector

    def generate_run_id(self) -> str:
        """Generate unique run ID"""
        return f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def substitute_parameters(self, sql: str, params: Dict) -> str:
        """
        Replace &parameter placeholders with actual values

        Args:
            sql: SQL string with &param placeholders
            params: Dict of parameter values

        Returns:
            Processed SQL string
        """
        processed_sql = sql
        if params:
            for key, value in params.items():
                # Handle both &param and &param. syntax
                pattern = r'&' + re.escape(key) + r'\.?'
                if isinstance(value, str):
                    # Check if it's a table/column name (no quotes) or a value (needs quotes)
                    if key in ['cf_pattern', 'table_name', 'schema']:
                        processed_sql = re.sub(pattern, str(value), processed_sql)
                    else:
                        processed_sql = re.sub(pattern, f"'{value}'", processed_sql)
                else:
                    processed_sql = re.sub(pattern, str(value), processed_sql)
        return processed_sql

    def execute_script_with_params(self, script: Dict, params: Dict) -> Any:
        """
        Execute a single script with parameter substitution

        Args:
            script: Script definition
            params: Execution parameters (including &cf_pattern)

        Returns:
            Script result value
        """
        if not self.oracle or not self.oracle.is_connected():
            raise Exception("Oracle not connected")

        sql = script['sql']

        # Substitute &parameters
        processed_sql = self.substitute_parameters(sql, params)

        # Execute
        result = self.oracle.execute_script(processed_sql)
        return result

    def run_sequential_analysis(self, scenarios: List[str], script_ids: List[str],
                                 user_params: Dict, cf_table_name: str = 'CF_PATTERNS',
                                 run_id: str = None) -> Dict:
        """
        Run scripts sequentially for each scenario

        Args:
            scenarios: List of scenario names (first should be 'Base')
            script_ids: List of script IDs in execution order
            user_params: User-provided parameters (report_date, etc.)
            cf_table_name: Name of the CF patterns table
            run_id: Optional run ID (will generate if not provided)

        Returns:
            Results dict with all scenario results
        """
        if not self.oracle or not self.oracle.is_connected():
            raise Exception("Oracle not connected")

        if not run_id:
            run_id = self.generate_run_id()

        results = {}
        all_script_results = []

        # Execute scripts for each scenario
        for scenario in scenarios:
            results[scenario] = {}

            for order, script_id in enumerate(script_ids, 1):
                script = self.script_manager.get_by_id(script_id)
                if not script:
                    continue

                # Build params with cf_pattern for this scenario
                exec_params = {**user_params}

                # The cf_pattern references the CF_PATTERNS table filtered by scenario
                # Scripts should use: WHERE SCENARIO_NAME = '&scenario_name' AND RUN_ID = '&run_id'
                exec_params['cf_pattern'] = cf_table_name
                exec_params['scenario_name'] = scenario
                exec_params['run_id'] = run_id

                try:
                    # Execute script
                    value = self.execute_script_with_params(script, exec_params)
                    results[scenario][script_id] = value

                    # Save to Oracle
                    self.oracle.save_analysis_result(
                        run_id=run_id,
                        scenario_name=scenario,
                        script_name=script['name'],
                        script_order=order,
                        result_value=float(value) if value else 0,
                        parameters=exec_params
                    )

                    all_script_results.append({
                        'scenario': scenario,
                        'script_id': script_id,
                        'script_name': script['name'],
                        'order': order,
                        'value': value,
                        'status': 'success'
                    })

                except Exception as e:
                    results[scenario][script_id] = {'error': str(e)}
                    all_script_results.append({
                        'scenario': scenario,
                        'script_id': script_id,
                        'script_name': script['name'],
                        'order': order,
                        'value': None,
                        'status': 'error',
                        'error': str(e)
                    })

        # Calculate comparison
        comparison = self.compare_results(results, scenarios[0] if scenarios else 'Base')

        return {
            'run_id': run_id,
            'results': results,
            'comparison': comparison,
            'execution_log': all_script_results,
            'executed_at': datetime.now().isoformat()
        }

    def run_analysis(self, scenarios: List[str], script_ids: List[str],
                     user_params: Dict, cashflows: Dict = None) -> Dict:
        """
        Run batch analysis for multiple scenarios and scripts
        (Legacy method - redirects to sequential analysis)

        Args:
            scenarios: List of scenario names (first is Base)
            script_ids: List of script IDs to execute
            user_params: User-provided parameters
            cashflows: Dict of scenario cashflows {name: {months, weights}}

        Returns:
            Results dict
        """
        if not self.oracle or not self.oracle.is_connected():
            raise Exception("Oracle not connected")

        run_id = self.generate_run_id()

        # Write cashflows to Oracle if provided
        if cashflows:
            for scenario_name, cf_data in cashflows.items():
                months = cf_data.get('months', list(range(1, 181)))
                weights = cf_data.get('weights', [])
                if weights:
                    self.oracle.write_cashflow_patterns(
                        run_id=run_id,
                        scenario_name=scenario_name,
                        months=months,
                        weights=weights
                    )

        # Run sequential analysis
        return self.run_sequential_analysis(
            scenarios=scenarios,
            script_ids=script_ids,
            user_params=user_params,
            run_id=run_id
        )

    def compare_results(self, results: Dict, base_name: str = 'Base') -> Dict:
        """
        Compare scenario results with base

        Args:
            results: Results dict {scenario: {script: value}}
            base_name: Name of base scenario

        Returns:
            Comparison dict
        """
        comparison = {}

        if base_name not in results:
            return comparison

        base_results = results[base_name]

        for script_id, base_value in base_results.items():
            if isinstance(base_value, dict) and 'error' in base_value:
                continue

            comparison[script_id] = {
                base_name: {
                    'value': base_value,
                    'diff': 0,
                    'diff_pct': 0
                }
            }

            for scenario, scenario_results in results.items():
                if scenario == base_name:
                    continue

                scenario_value = scenario_results.get(script_id)
                if isinstance(scenario_value, dict) and 'error' in scenario_value:
                    comparison[script_id][scenario] = {'error': scenario_value['error']}
                    continue

                if scenario_value is not None and base_value is not None and base_value != 0:
                    diff = scenario_value - base_value
                    diff_pct = (diff / base_value) * 100
                else:
                    diff = 0
                    diff_pct = 0

                comparison[script_id][scenario] = {
                    'value': scenario_value,
                    'diff': diff,
                    'diff_pct': diff_pct
                }

        return comparison

    def run_script_by_patterns(self, script_id: str, run_id: str, pattern_names: List[str],
                               user_params: Dict, cf_table_name: str = 'CF_PATTERNS') -> Dict:
        """
        Tek script'i her pattern için çalıştır; &cf_pattern, &run_id, &scenario_name substitute edilir.
        Her çalıştırma tek bir pl_value döndürür.
        Returns: { 'run_id': str, 'pl_values': { pattern_name: value } }
        """
        if not self.oracle or not self.oracle.is_connected():
            raise Exception("Oracle not connected")

        script = self.script_manager.get_by_id(script_id)
        if not script:
            raise Exception("Script bulunamadı")

        pl_values = {}
        for pattern_name in pattern_names:
            exec_params = {**user_params}
            exec_params['cf_pattern'] = cf_table_name
            exec_params['run_id'] = run_id
            exec_params['scenario_name'] = pattern_name
            try:
                value = self.execute_script_with_params(script, exec_params)
                pl_values[pattern_name] = float(value) if value is not None else None
            except Exception as e:
                pl_values[pattern_name] = {'error': str(e)}

        return {'run_id': run_id, 'pl_values': pl_values}

    def format_results_table(self, results: Dict, comparison: Dict) -> List[Dict]:
        """
        Format results as a table for display

        Args:
            results: Results dict
            comparison: Comparison dict

        Returns:
            List of row dicts for table display
        """
        rows = []

        scenarios = list(results.keys())

        # Get all script IDs
        script_ids = set()
        for scenario_results in results.values():
            script_ids.update(scenario_results.keys())

        for script_id in sorted(script_ids):
            script = self.script_manager.get_by_id(script_id)
            script_name = script['name'] if script else script_id

            row = {'script': script_name, 'script_id': script_id}

            for scenario in scenarios:
                value = results.get(scenario, {}).get(script_id)
                if isinstance(value, dict) and 'error' in value:
                    row[scenario] = 'Error'
                else:
                    row[scenario] = value

                # Add diff for non-base scenarios
                if comparison.get(script_id, {}).get(scenario):
                    comp = comparison[script_id][scenario]
                    if 'diff_pct' in comp:
                        row[f'{scenario}_diff'] = comp['diff']
                        row[f'{scenario}_diff_pct'] = comp['diff_pct']

            rows.append(row)

        return rows


# Global instances
script_manager = ScriptManager()
analysis_engine = AnalysisEngine()
