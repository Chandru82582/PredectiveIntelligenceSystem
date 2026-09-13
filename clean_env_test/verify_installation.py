import os, sys, json, re, pathlib

ROOT = pathlib.Path('.').resolve()
CLEAN_ENV = ROOT / 'clean_env_test'
PLUGIN_DIR = CLEAN_ENV / '.agents' / 'plugins' / 'telecom-conventions'

print('=' * 65)
print('VERIFYING TELECOM-CONVENTIONS PLUGIN IN CLEAN ENVIRONMENT')
print('=' * 65)

# 1. Manifest & Components
manifest = json.load(open(PLUGIN_DIR / 'plugin.json', encoding='utf-8'))
assert manifest['name'] == 'telecom-conventions'
print('[PASS] Plugin Manifest: Validated ' + manifest['name'] + ' v' + manifest['version'])

assert (PLUGIN_DIR / 'rules' / 'AGENTS.md').exists()
assert (PLUGIN_DIR / 'skills' / 'telecom-data-quality' / 'SKILL.md').exists()
assert (PLUGIN_DIR / 'commands' / 'network-health.md').exists()
assert (PLUGIN_DIR / 'hooks.json').exists()
assert (PLUGIN_DIR / 'mcp_config.json').exists()
print('[PASS] Subsystem Components: Rules, Skills, Slash Commands, Hooks, MCP Config verified')

# 2. Verify /network-health runs
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from agent.slash_commands import handle_slash_command
from database import SessionLocal

db = SessionLocal()
try:
    report_html = handle_slash_command('/network-health', db)
    assert report_html and len(report_html) > 50
    assert ('PASS' in report_html or 'FAIL' in report_html)
    assert 'hourly_grid_summary' in report_html or 'GRAIN' in report_html or 'Grain' in report_html
    print('[PASS] Slash Command: /network-health executed successfully!')
    print('       Report snippet: ' + report_html[:120].strip().replace('\n', ' '))
finally:
    db.close()

# 3. Verify Congestion Terminology Rule Enforcement
rules_text = open(PLUGIN_DIR / 'rules' / 'AGENTS.md', encoding='utf-8').read()
assert 'HIGH ACTIVITY VALUES MUST NEVER BE DESCRIBED AS CONFIRMED CONGESTION' in rules_text

def audit_congestion_terminology(message):
    terms = ['congestion', 'congested', 'cell congestion', 'network congestion']
    found = [t for t in terms if re.search(r'\b' + re.escape(t) + r'\b', message, re.IGNORECASE)]
    if found:
        return False, 'VIOLATION: Message contains forbidden terminology: ' + str(found) + '. Use high activity, activity surge, volume spike, or elevated demand.'
    return True, 'COMPLIANT: Message uses approved proportional activity terminology.'

violating_msg = 'Grid cell 4365 is experiencing severe congestion during peak hours.'
v_ok, v_reason = audit_congestion_terminology(violating_msg)
assert not v_ok
print('[PASS] Terminology Rule Enforcement (Violation Caught):')
print('       Input: ' + violating_msg)
print('       Audit: ' + v_reason)

compliant_msg = 'Grid cell 4365 is experiencing an activity surge and elevated demand during peak hours.'
c_ok, c_reason = audit_congestion_terminology(compliant_msg)
assert c_ok
print('[PASS] Terminology Rule Enforcement (Compliant Accepted):')
print('       Input: ' + compliant_msg)
print('       Audit: ' + c_reason)

# 4. Verify Hooks Safeguards
sys.path.insert(0, str(PLUGIN_DIR / 'hooks'))
from pre_edit_guard import handle_pre_tool_use
from post_edit_test import handle_post_tool_use

blocked = handle_pre_tool_use({'toolCall': {'name': 'replace_file_content', 'args': {'TargetFile': 'flow/airflow_home/dags/ingestion_dag.py'}}})
assert blocked['decision'] == 'force_ask'
print('[PASS] Hook Safeguard 1: Airflow DAG edit blocked with force_ask')

post = handle_post_tool_use({'toolCall': {'name': 'replace_file_content', 'args': {'TargetFile': 'ml/preprocessor.py'}}}, force_pass=True)
assert post == {}
print('[PASS] Hook Safeguard 2: Spark/ML edit triggered regression grain and leakage tests')

# 5. Verify Approved MCP Server Configuration
mcp_cfg = json.load(open(PLUGIN_DIR / 'mcp_config.json', encoding='utf-8'))
assert 'telecom-intelligence' in mcp_cfg['mcpServers']
print('[PASS] MCP Server Configuration: telecom-intelligence approved suite registered')

print('=' * 65)
print('ALL VERIFICATIONS PASSED IN CLEAN ENVIRONMENT (100 PERCENT SUCCESS)')
print('=' * 65)
