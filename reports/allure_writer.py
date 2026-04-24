# reports/allure_writer.py
"""
Generate Allure JSON results without pytest.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List


class AllureWriter:
    """Write Allure-compatible JSON results."""
    
    def __init__(self, output_dir: str = "allure-results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def write_test_result(self, test_data: Dict):
        """
        Write single test result in Allure format.
        
        Args:
            test_data: Dict with keys: id, input, response, latency_ms, 
                      verdict, judge, heuristic_results
        """
        test_id = test_data.get("id", "unknown")
        verdict = test_data.get("verdict", "FAIL")
        
        # Map verdict to Allure status
        status = "passed" if verdict == "PASS" else "failed"
        
        # Generate UUID for this test
        test_uuid = str(uuid.uuid4())
        
        # Build Allure result structure
        result = {
            "uuid": test_uuid,
            "historyId": test_id,
            "name": f"Test: {test_id}",
            "fullName": f"verdictai.{test_id}",
            "status": status,
            "statusDetails": self._get_status_details(test_data),
            "start": int(datetime.now().timestamp() * 1000),
            "stop": int(datetime.now().timestamp() * 1000),
            "labels": [
                {"name": "suite", "value": "VerdictAI"},
                {"name": "severity", "value": "critical" if status == "failed" else "normal"},
                {"name": "framework", "value": "verdictai"}
            ],
            "parameters": [],
            "attachments": self._create_attachments(test_data, test_uuid),
            "steps": self._create_steps(test_data)
        }
        
        # Write JSON file
        result_file = self.output_dir / f"{test_uuid}-result.json"
        result_file.write_text(json.dumps(result, indent=2), encoding='utf-8')
    
    def _get_status_details(self, test_data: Dict) -> Dict:
        """Extract failure message if test failed."""
        if test_data.get("verdict") == "FAIL":
            judge = test_data.get("judge", {})
            reason = judge.get("reason", "Test failed")
            return {
                "message": reason,
                "trace": ""
            }
        return {}
    
    def _create_attachments(self, test_data: Dict, test_uuid: str) -> List[Dict]:
        """Create attachments for prompt, response, judge result."""
        attachments = []
        
        # Attach input prompt
        input_file = self.output_dir / f"{test_uuid}-input.txt"
        input_file.write_text(test_data.get("input", ""), encoding='utf-8')
        attachments.append({
            "name": "Input Prompt",
            "source": f"{test_uuid}-input.txt",
            "type": "text/plain"
        })
        
        # Attach LLM response
        response_file = self.output_dir / f"{test_uuid}-response.txt"
        response_file.write_text(test_data.get("response", ""), encoding='utf-8')
        attachments.append({
            "name": "LLM Response",
            "source": f"{test_uuid}-response.txt",
            "type": "text/plain"
        })
        
        # Attach judge result if exists
        if test_data.get("judge"):
            judge = test_data["judge"]
            judge_text = f"Score: {judge.get('score')}\nVerdict: {judge.get('verdict')}\nReason: {judge.get('reason', 'N/A')}"
            judge_file = self.output_dir / f"{test_uuid}-judge.txt"
            judge_file.write_text(judge_text, encoding='utf-8')
            attachments.append({
                "name": "Judge Result",
                "source": f"{test_uuid}-judge.txt",
                "type": "text/plain"
            })
        
        return attachments
    
    def _create_steps(self, test_data: Dict) -> List[Dict]:
        """Create execution steps for Allure timeline."""
        steps = []
        
        # Step 1: Get LLM response
        steps.append({
            "name": f"Get LLM Response ({test_data.get('latency_ms', 0)}ms)",
            "status": "passed",
            "start": int(datetime.now().timestamp() * 1000),
            "stop": int(datetime.now().timestamp() * 1000)
        })
        
        # Step 2: Heuristic checks
        heuristic_pass = test_data.get("heuristic_pass", False)
        steps.append({
            "name": "Run Heuristic Assertions",
            "status": "passed" if heuristic_pass else "failed",
            "start": int(datetime.now().timestamp() * 1000),
            "stop": int(datetime.now().timestamp() * 1000)
        })
        
        # Step 3: LLM judge
        if test_data.get("judge"):
            judge_verdict = test_data["judge"].get("verdict", "FAIL")
            steps.append({
                "name": f"LLM Judge (Score: {test_data['judge'].get('score')})",
                "status": "passed" if judge_verdict == "PASS" else "failed",
                "start": int(datetime.now().timestamp() * 1000),
                "stop": int(datetime.now().timestamp() * 1000)
            })
        
        return steps
    
    def write_environment(self, env_data: Dict):
        """Write environment properties file."""
        env_file = self.output_dir / "environment.properties"
        lines = [f"{k}={v}" for k, v in env_data.items()]
        env_file.write_text("\n".join(lines), encoding='utf-8')
    
    def write_categories(self):
        """Write test categories for Allure."""
        categories = [
            {
                "name": "Regression Failures",
                "matchedStatuses": ["failed"],
                "messageRegex": ".*regression.*"
            },
            {
                "name": "Judge Failures",
                "matchedStatuses": ["failed"],
                "messageRegex": ".*judge.*"
            }
        ]
        
        cat_file = self.output_dir / "categories.json"
        cat_file.write_text(json.dumps(categories, indent=2), encoding='utf-8')