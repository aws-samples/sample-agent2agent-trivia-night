import json
import time
from typing import List

from strands import tool
from strands_tools.code_interpreter import AgentCoreCodeInterpreter
from strands_tools.code_interpreter.models import ExecuteCodeAction, ExecuteCommandAction
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter as CodeInterpreterClient

from config import REGION, S3_BUCKET

# ---------------------------------------------------------------------------
# CodeInterpreter sandbox setup
# ---------------------------------------------------------------------------

ci_client = CodeInterpreterClient(REGION)
INTERPRETER_NAME = "statistician_interpreter"


def _get_or_create_interpreter() -> str:
    """Return the CodeInterpreter ID, creating one if it doesn't exist."""
    try:
        ci_response = ci_client.create_code_interpreter(
            name=INTERPRETER_NAME,
            execution_role_arn=_get_execution_role(),
            description="Code interpreter with S3 access for statistician agent",
            network_configuration={"networkMode": "PUBLIC"},
        )
        identifier = ci_response["codeInterpreterId"]

        # Wait until ready
        while True:
            status = ci_client.get_code_interpreter(interpreter_id=identifier).get("status", "UNKNOWN")
            if status == "READY":
                break
            if status in ("FAILED", "DELETING"):
                raise RuntimeError(f"Code interpreter entered unexpected status: {status}")
            time.sleep(5)

        return identifier

    except ci_client.control_plane_client.exceptions.ConflictException:
        # Already exists — look it up
        for ci in ci_client.list_code_interpreters().get("codeInterpreterSummaries", []):
            if ci["name"] == INTERPRETER_NAME:
                return ci["codeInterpreterId"]
        raise RuntimeError(f"Code interpreter '{INTERPRETER_NAME}' conflict but could not find existing one")


def _get_execution_role() -> str:
    """Resolve the execution role ARN from environment or helper."""
    import os

    role_arn = os.getenv("STATISTICIAN_EXECUTION_ROLE_ARN", "")
    if not role_arn:
        try:
            from boto3_helper import get_role_arn
            role_arn = get_role_arn("BedrockAgentCoreStrands")
        except ImportError:
            raise RuntimeError(
                "Set STATISTICIAN_EXECUTION_ROLE_ARN or provide utils.boto3_helper.get_role_arn"
            )
    return role_arn


interpreter_id = _get_or_create_interpreter()
code_interpreter = AgentCoreCodeInterpreter(
    region=REGION,
    identifier=interpreter_id,
    session_name="statistician-session",
)

_sandbox_initialized = False


def ensure_sandbox():
    """Install required packages in the CodeInterpreter sandbox on first use."""
    global _sandbox_initialized
    if not _sandbox_initialized:
        code_interpreter.execute_command(
            ExecuteCommandAction(
                type="executeCommand",
                command="pip install lifelines boto3 pandas numpy matplotlib",
            )
        )
        _sandbox_initialized = True


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def run_code(code: str) -> str:
    """Execute Python code in the CodeInterpreter sandbox.

    Use this tool to write and run any Python code, including creating
    charts, performing calculations, or processing data.

    The sandbox has matplotlib, pandas, numpy, lifelines, and boto3 available.
    To save charts to S3, use boto3 to upload to the bucket and prefix shown below.

    S3 bucket: {s3_bucket}
    S3 prefix: graphs/

    Args:
        code: Python code to execute in the sandbox.

    Returns:
        Output from the code execution.
    """.format(s3_bucket=S3_BUCKET)
    ensure_sandbox()
    result = code_interpreter.execute_code(
        ExecuteCodeAction(type="executeCode", code=code, language="python")
    )
    return json.dumps(result, indent=2)


@tool
def plot_kaplan_meier(
    biomarker_name: str,
    duration_baseline: List[float],
    duration_condition: List[float],
    event_baseline: List[int],
    event_condition: List[int],
) -> str:
    """Create a Kaplan-Meier survival plot comparing two groups.

    Args:
        biomarker_name: Name of the biomarker being analyzed.
        duration_baseline: Survival duration in days for baseline group.
        duration_condition: Survival duration in days for condition group.
        event_baseline: Survival events for baseline (0=alive, 1=dead).
        event_condition: Survival events for condition (0=alive, 1=dead).

    Returns:
        Result of the Kaplan-Meier plot creation.
    """
    ensure_sandbox()

    code = f"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from lifelines import KaplanMeierFitter
import io
import boto3

biomarker_name = {repr(biomarker_name)}
duration_baseline = {duration_baseline}
event_baseline = {event_baseline}
duration_condition = {duration_condition}
event_condition = {event_condition}
s3_bucket = {repr(S3_BUCKET)}

kmf_baseline = KaplanMeierFitter()
kmf_baseline.fit(durations=duration_baseline, event_observed=event_baseline, label='<=10')

kmf_condition = KaplanMeierFitter()
kmf_condition.fit(durations=duration_condition, event_observed=event_condition, label='>10')

fig, ax = plt.subplots(figsize=(10, 6))
kmf_baseline.plot_survival_function(ax=ax, ci_show=True, color='blue')
kmf_condition.plot_survival_function(ax=ax, ci_show=True, color='darkorange')
ax.set_title(biomarker_name)
ax.set_xlabel('Timeline (days)')
ax.set_ylabel('Survival Probability')
ax.legend(loc='upper right')
ax.grid(True, alpha=0.3)

img_data = io.BytesIO()
fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
img_data.seek(0)

s3 = boto3.resource('s3')
key = f'graphs/{{biomarker_name}}_KMplot.png'
s3.Bucket(s3_bucket).put_object(Body=img_data, ContentType='image/png', Key=key)
print(f"Kaplan-Meier plot saved to s3://{{s3_bucket}}/{{key}}")
"""
    result = code_interpreter.execute_code(
        ExecuteCodeAction(type="executeCode", code=code, language="python")
    )
    return json.dumps(result, indent=2)


@tool
def fit_survival_regression(bucket: str, key: str) -> str:
    """Fit a Cox Proportional Hazards survival regression model using data from S3.

    Args:
        bucket: S3 bucket where the data is stored.
        key: JSON file name in the S3 bucket containing the data for model fitting.

    Returns:
        Results of the survival regression analysis.
    """
    ensure_sandbox()

    code = f"""
import json
import boto3
import pandas as pd
import numpy as np
from lifelines import CoxPHFitter

bucket = {repr(bucket)}
key = {repr(key)}

s3 = boto3.client('s3')
obj = s3.get_object(Bucket=bucket, Key=key)
data = json.loads(obj['Body'].read().decode('utf-8'))

columns = [col['name'] for col in data['ColumnMetadata']]
processed_records = []
for record in data['Records']:
    row = []
    for value in record:
        if 'stringValue' in value:
            row.append(value['stringValue'])
        elif 'doubleValue' in value:
            row.append(value['doubleValue'])
        elif 'booleanValue' in value:
            row.append(value['booleanValue'])
        else:
            row.append(None)
    processed_records.append(row)

df = pd.DataFrame(processed_records, columns=columns)
df['survival_status'] = df['survival_status'].map({{False: 0, True: 1}})

df.loc[df['survival_status'] == 0, 'survival_duration'] = 100
for biomarker in ['gdf15', 'lrig1', 'cdh2', 'postn', 'vcan']:
    if biomarker in df.columns:
        mask = df['survival_status'] == 0
        df.loc[mask, biomarker] = df.loc[mask, biomarker] + (np.random.rand(mask.sum()) * 30)

df_numeric = df.select_dtypes(include='number')

cph = CoxPHFitter(penalizer=0.01)
cph.fit(df_numeric, duration_col='survival_duration', event_col='survival_status')
summary = cph.summary

print("Cox Proportional Hazards Regression Summary:")
print(summary.to_string())
"""
    result = code_interpreter.execute_code(
        ExecuteCodeAction(type="executeCode", code=code, language="python")
    )
    return json.dumps(result, indent=2)


statistician_tools = [run_code, plot_kaplan_meier, fit_survival_regression]
