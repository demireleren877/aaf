"""
Analysis Engine Module
Handles batch execution of SQL scripts and result comparison
"""
import json
import uuid
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

    def prepare_parameters(self, script: Dict, user_params: Dict,
                          run_id: str, scenario_name: str) -> Dict:
        """
        Prepare parameters for script execution

        Args:
            script: Script definition
            user_params: User-provided parameters
            run_id: Current run ID
            scenario_name: Current scenario name

        Returns:
            Complete parameter dict
        """
        params = {}

        # Add system parameters
        params['run_id'] = run_id
        params['scenario_name'] = scenario_name

        # Process script parameters
        for param_def in script.get('parameters', []):
            name = param_def['name']

            # Skip system params already set
            if name in ['run_id', 'scenario_name']:
                continue

            # Use user value or default
            if name in user_params:
                value = user_params[name]
            elif 'default' in param_def:
                value = param_def['default']
            else:
                value = None

            # Type conversion
            param_type = param_def.get('type', 'text')
            if value is not None:
                if param_type == 'number':
                    value = float(value)
                elif param_type == 'date':
                    # Keep as string, Oracle will handle
                    pass

            params[name] = value

        return params

    def execute_script(self, script_id: str, params: Dict) -> Any:
        """
        Execute a single script

        Args:
            script_id: Script identifier
            params: Execution parameters

        Returns:
            Script result value
        """
        if not self.oracle or not self.oracle.is_connected():
            raise Exception("Oracle not connected")

        script = self.script_manager.get_by_id(script_id)
        if not script:
            raise Exception(f"Script not found: {script_id}")

        sql = script['sql']
        result = self.oracle.execute_script(sql, params)

        return result

    def run_analysis(self, scenarios: List[str], script_ids: List[str],
                     user_params: Dict, cashflows: Dict = None) -> Dict:
        """
        Run batch analysis for multiple scenarios and scripts

        Args:
            scenarios: List of scenario names (first is Base)
            script_ids: List of script IDs to execute
            user_params: User-provided parameters
            cashflows: Dict of scenario cashflows {name: {quarters, weights}}

        Returns:
            Results dict: {
                'run_id': str,
                'results': {scenario: {script: value}},
                'comparison': {script: {scenario: value, diff, diff_pct}}
            }
        """
        if not self.oracle or not self.oracle.is_connected():
            raise Exception("Oracle not connected")

        run_id = self.generate_run_id()
        results = {}

        # Write cashflows to Oracle if provided
        if cashflows:
            for scenario_name, cf_data in cashflows.items():
                self.oracle.write_cashflow_patterns(
                    run_id=run_id,
                    scenario_name=scenario_name,
                    quarters=cf_data['quarters'],
                    weights=cf_data['weights']
                )

        # Execute scripts for each scenario
        for scenario in scenarios:
            results[scenario] = {}

            for script_id in script_ids:
                script = self.script_manager.get_by_id(script_id)
                if not script:
                    continue

                # Prepare parameters
                params = self.prepare_parameters(
                    script, user_params, run_id, scenario
                )

                try:
                    # Execute script
                    value = self.oracle.execute_script(script['sql'], params)
                    results[scenario][script_id] = value

                    # Save to Oracle
                    self.oracle.save_analysis_result(
                        run_id=run_id,
                        scenario_name=scenario,
                        script_name=script['name'],
                        result_value=float(value) if value else 0,
                        parameters=params
                    )
                except Exception as e:
                    results[scenario][script_id] = {'error': str(e)}

        # Calculate comparison
        comparison = self.compare_results(results, scenarios[0] if scenarios else 'Base')

        return {
            'run_id': run_id,
            'results': results,
            'comparison': comparison,
            'executed_at': datetime.now().isoformat()
        }

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
